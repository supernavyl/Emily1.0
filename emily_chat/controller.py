"""Controller wiring UI signals to database and streaming engine.

Owns the lifecycle of the database, background thread, persona engine,
and streaming engine.  Accumulates session statistics and dispatches
conversation-level actions (edit, retry, branch, feedback).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from PySide6.QtCore import QObject

from emily_chat.config import AppSettings
from emily_chat.profiles import load_profiles, resolve_model_for_skill
from emily_chat.emily.persona import EmilyPersonaEngine, PrivacyGrants, SessionContext
from emily_chat.emily.skills import EmilySkill, get_skill, save_custom_skill
from emily_chat.export.engine import ExportEngine
from emily_chat.models.auto_router import EmilyAutoRouter, classify_request
from emily_chat.models.provider_factory import (
    ProviderUnavailableError,
    get_provider,
)
from emily_chat.models.registry import (
    ModelSpec,
    get_default_model,
    get_model,
    register_dynamic_model,
)
from emily_chat.models.streaming_engine import (
    EmilyStreamingEngine,
    GenerationSettings,
    StreamChunk,
)
from emily_chat.storage.database import ConversationDatabase
from emily_chat.storage.models import ConversationSummary
from emily_chat.ui.async_bridge import AsyncRunner
from emily_chat.ui.conversation_stream import ConversationStream
from emily_chat.ui.input_panel import InputPanel
from emily_chat.ui.left_sidebar import LeftSidebar
from emily_chat.ui.right_panel import RightPanel, compute_session_stats
from emily_chat.ui.search_overlay import GlobalSearchOverlay
from emily_chat.ui.top_bar import ConversationTopBar


class ChatController(QObject):
    """Mediates between the UI, database, persona engine, and streaming engine."""

    def __init__(
        self,
        sidebar: LeftSidebar,
        conversation_stream: ConversationStream,
        input_panel: InputPanel,
        right_panel: RightPanel,
        settings: AppSettings,
        top_bar: ConversationTopBar | None = None,
        search_overlay: GlobalSearchOverlay | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sidebar = sidebar
        self._stream_view = conversation_stream
        self._input_panel = input_panel
        self._right_panel = right_panel
        self._top_bar = top_bar
        self._search_overlay = search_overlay
        self._settings = settings

        self._db = ConversationDatabase()
        self._runner = AsyncRunner(self)
        self._persona = EmilyPersonaEngine()
        self._engine = EmilyStreamingEngine(self._persona)
        self._privacy_grants = PrivacyGrants()
        self._auto_router = EmilyAutoRouter()
        self._export_engine = ExportEngine()

        self._pending: dict[str, str] = {}
        self._active_conversation_id: str | None = None
        self._active_stream_token: str | None = None
        self._interrupt = asyncio.Event()

        # Accumulation state for the current generation
        self._gen_thinking_text = ""
        self._gen_response_text = ""
        self._gen_usage: dict[str, Any] = {}
        self._gen_model_spec: ModelSpec | None = None

        # Cached conversation history for LLM context
        self._conversation_messages: list[dict[str, str]] = []

        # Session-level statistics (accumulated across messages)
        self._session_messages: list[dict[str, Any]] = []

        # --- wire runner signals ---
        self._runner.result_ready.connect(self._on_result)
        self._runner.error_occurred.connect(self._on_error)
        self._runner.chunk_received.connect(self._on_chunk)
        self._runner.stream_done.connect(self._on_stream_done)
        self._runner.loop_ready.connect(self._on_runner_loop_ready)

        # --- wire sidebar signals ---
        self._sidebar.new_conversation.connect(self._create_conversation)
        self._sidebar.conversation_selected.connect(self._select_conversation)
        self._sidebar.rename_requested.connect(self._rename_conversation)
        self._sidebar.pin_requested.connect(self._pin_conversation)
        self._sidebar.archive_requested.connect(self._archive_conversation)
        self._sidebar.delete_requested.connect(self._delete_conversation)
        self._sidebar.duplicate_requested.connect(self._duplicate_conversation)
        self._sidebar.search_requested.connect(self._search)
        self._sidebar.skill_activated.connect(self._on_skill_changed)
        self._sidebar.custom_skill_requested.connect(self._on_custom_skill_requested)
        self._sidebar.export_requested.connect(self._on_sidebar_export)

        # --- wire input signals ---
        self._input_panel.message_submitted.connect(self._send_message)
        self._input_panel.stop_requested.connect(self._stop_generation)
        self._input_panel.slash_command.connect(self._on_slash_command)
        self._input_panel.web_search_toggled.connect(self._on_web_search_toggled)
        self._input_panel.quick_skill_override.connect(self._on_quick_skill_override)

        self._web_search_enabled = False
        self._one_shot_skill: str | None = None

        # --- wire conversation stream signals (Phase 12) ---
        self._stream_view.edit_requested.connect(self._on_edit_message)
        self._stream_view.resend_requested.connect(self._on_resend_message)
        self._stream_view.retry_requested.connect(self._on_retry_message)
        self._stream_view.branch_requested.connect(self._on_branch_message)
        self._stream_view.feedback_given.connect(self._on_feedback)

        # --- wire top bar signals (Phase 14) ---
        if self._top_bar is not None:
            self._top_bar.model_changed.connect(self._on_model_changed)
            self._top_bar.skill_changed.connect(self._on_skill_changed)
            self._top_bar.clear_requested.connect(
                lambda: self._stream_view.clear_messages()
            )
            self._top_bar.set_active_model(self._settings.default_model)
            self._top_bar.set_active_skill(self._settings.active_skill_id)
            self._top_bar.export_requested.connect(self._on_topbar_export)
            self._top_bar.emily_editor_requested.connect(self._on_emily_editor_requested)

        # --- wire search overlay signals (Phase 18) ---
        if self._search_overlay is not None:
            self._search_overlay.search_query.connect(self._on_search_query)
            self._search_overlay.conversation_opened.connect(self._select_conversation)
            self._search_overlay.command_executed.connect(self._on_search_command)

    # ── lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background thread; DB init runs when the loop is ready."""
        self._runner.start()

    def _on_runner_loop_ready(self) -> None:
        """Called when AsyncRunner's event loop is running; submit DB init."""
        token = self._runner.submit(self._db.init())
        self._pending[token] = "init"

    async def _discover_ollama_models(self) -> int:
        """Discover Ollama models and register them in the registry.

        Returns:
            Number of models registered (excluding the static ollama-local).
        """
        import os
        from emily_chat.models.providers.ollama import OllamaProvider

        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        provider = OllamaProvider(base_url=host)
        discovered = await provider.discover_models()
        await provider.close()
        count = 0
        for m in discovered:
            name = m.get("name", "").strip()
            if not name:
                continue
            key = "ollama-" + name.replace(":", "-")
            if get_model(key) is not None:
                continue
            spec = OllamaProvider.create_local_spec(name)
            register_dynamic_model(key, spec)
            count += 1
        return count

    async def _discover_llamacpp_models(self) -> int:
        """Discover GGUF models from config and register them in the registry.

        Returns:
            Number of models registered.
        """
        from emily_chat.models.providers.llamacpp import list_gguf_models

        items = list_gguf_models()
        for key, spec in items:
            if get_model(key) is None:
                register_dynamic_model(key, spec)
        return len(items)

    def shutdown(self) -> None:
        """Close the database, providers, and stop the background thread."""
        self._interrupt.set()
        if self._runner.isRunning():
            from emily_chat.models.provider_factory import close_all

            self._runner.submit(close_all())
            self._runner.submit(self._db.close())
        self._runner.shutdown()

    # ── sidebar actions ─────────────────────────────────────────

    def _create_conversation(self) -> None:
        token = self._runner.submit(self._db.create_conversation())
        self._pending[token] = "create"

    def _select_conversation(self, conversation_id: str) -> None:
        self._active_conversation_id = conversation_id
        self._settings.last_conversation_id = conversation_id
        self._settings.save()
        token = self._runner.submit(self._db.get_messages(conversation_id))
        self._pending[token] = "load_messages"

    def _rename_conversation(self, conversation_id: str) -> None:
        token = self._runner.submit(
            self._db.rename_conversation(conversation_id, "Renamed")
        )
        self._pending[token] = "refresh"

    def _pin_conversation(self, conversation_id: str, pinned: bool) -> None:
        token = self._runner.submit(
            self._db.pin_conversation(conversation_id, pinned)
        )
        self._pending[token] = "refresh"

    def _archive_conversation(self, conversation_id: str) -> None:
        token = self._runner.submit(self._db.archive_conversation(conversation_id))
        self._pending[token] = "refresh"

    def _delete_conversation(self, conversation_id: str) -> None:
        token = self._runner.submit(self._db.delete_conversation(conversation_id))
        self._pending[token] = "refresh"

    def _duplicate_conversation(self, conversation_id: str) -> None:
        token = self._runner.submit(self._db.duplicate_conversation(conversation_id))
        self._pending[token] = "refresh"

    def _search(self, query: str) -> None:
        if not query.strip():
            self._reload_conversations()
            return
        token = self._runner.submit(self._db.search_fulltext(query))
        self._pending[token] = "search"

    # ── send message + streaming ────────────────────────────────

    def _send_message(self, text: str) -> None:
        """Handle a user message: save to DB, then stream LLM response."""
        conv_id = self._active_conversation_id
        if conv_id is None:
            # Auto-create a conversation if none is selected
            self._pending_user_text = text
            token = self._runner.submit(self._db.create_conversation())
            self._pending[token] = "create_then_send"
            return

        self._do_send(conv_id, text)

    def _do_send(self, conv_id: str, text: str) -> None:
        """Save user message and start streaming."""
        # Show in UI immediately
        self._stream_view.append_user_message(text)

        # Save user message to DB (fire-and-forget for speed)
        self._runner.submit(
            self._db.add_message(conv_id, "user", text)
        )

        # Append to in-memory conversation history for LLM context
        self._conversation_messages.append({"role": "user", "content": text})

        # Reset generation state
        self._gen_thinking_text = ""
        self._gen_response_text = ""
        self._gen_usage = {}
        self._interrupt.clear()

        # Prepare the stream
        self._stream_view.start_emily_message()
        self._right_panel.clear()
        self._input_panel.set_generating(True)

        # Resolve model (from active profile + skill, or default_model)
        skill = self._get_active_skill()
        profiles = load_profiles()
        model_id = resolve_model_for_skill(
            profiles,
            self._settings.active_profile_id,
            self._settings.active_skill_id,
            fallback_model=self._settings.default_model,
        )

        if model_id == "auto":
            routing_req = classify_request(text, skill)
            model_spec = self._auto_router.route(routing_req)
            if self._top_bar:
                self._top_bar.set_live_stats({"routed_model": model_spec.display})
        else:
            model_spec = get_model(model_id)
            if model_spec is None:
                _, model_spec = get_default_model()

        self._gen_model_spec = model_spec

        # Resolve provider
        try:
            provider = get_provider(model_spec)
        except ProviderUnavailableError as exc:
            self._stream_view.append_emily_text(f"\n\n[{exc}]\n")
            self._stream_view.finish_emily_message()
            self._input_panel.set_generating(False)
            return

        # Build system prompt
        is_probe = self._persona.detect_identity_probe(text)
        session_ctx = SessionContext(
            current_datetime=datetime.now(tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            ),
            provider_name=model_spec.provider,
        )
        system_prompt = self._persona.build_system_prompt(
            skill, self._privacy_grants, session_ctx
        )
        if is_probe:
            system_prompt = (
                self._persona.get_identity_reinforcement() + "\n\n" + system_prompt
            )

        # Full conversation history for LLM context
        messages = list(self._conversation_messages)

        settings = GenerationSettings(
            temperature=skill.temperature,
            max_tokens=8192,
            thinking_budget=8000 if skill.enable_thinking and model_spec.thinking else 0,
        )

        # Start streaming via the async runner
        engine = self._engine

        async def _stream_gen():
            async for chunk in engine.stream_chunks(
                provider, model_spec, messages, system_prompt, settings,
            ):
                yield chunk

        self._active_stream_token = self._runner.submit_streaming(_stream_gen())

    def _stop_generation(self) -> None:
        """Cancel the active generation."""
        self._interrupt.set()
        if self._active_stream_token is not None:
            self._runner.cancel_stream(self._active_stream_token)
            self._active_stream_token = None
        self._finish_generation(stopped=True)

    def _get_active_skill(self) -> EmilySkill:
        """Return the currently active skill."""
        skill = get_skill(self._settings.active_skill_id)
        if skill is None:
            from emily_chat.emily.skills import EmilySkill
            skill = EmilySkill(name="Normal Chat")
        return skill

    # ── top bar handlers ───────────────────────────────────────

    def _on_model_changed(self, model_key: str) -> None:
        """Handle model selection from the top bar.

        Args:
            model_key: Registry key or ``"auto"``.
        """
        self._settings.default_model = model_key
        self._settings.save()

    def _on_skill_changed(self, skill_id: str) -> None:
        """Handle skill selection from the top bar.

        Args:
            skill_id: Skill key.
        """
        self._settings.active_skill_id = skill_id
        self._settings.save()
        skill = get_skill(skill_id)
        if skill:
            placeholders = {
                "code": "Describe the code you need or paste code to review\u2026",
                "research": "What would you like me to research?",
                "translate": "Paste text to translate\u2026",
                "writing": "What would you like me to write or edit?",
            }
            self._input_panel.set_placeholder(
                placeholders.get(skill_id, "Ask Emily anything\u2026")
            )

    # ── search overlay handlers (Phase 18) ─────────────────────

    def _on_search_query(self, query: str) -> None:
        """Handle search query from the overlay.

        Args:
            query: The search query text.
        """
        if not query.strip():
            return
        token = self._runner.submit(self._db.search_fulltext(query))
        self._pending[token] = "overlay_search"

    def _on_search_command(self, cmd_id: str) -> None:
        """Handle a command from the search overlay.

        Args:
            cmd_id: The command identifier.
        """
        if cmd_id == "new":
            self._create_conversation()
        elif cmd_id == "export":
            if self._top_bar:
                self._top_bar.export_requested.emit("markdown")
        elif cmd_id == "fork":
            pass
        elif cmd_id == "settings":
            pass

    # ── export handlers (Phase 19) ──────────────────────────────

    def _on_sidebar_export(self, conv_id: str, fmt: str) -> None:
        """Handle export request from the sidebar context menu.

        Args:
            conv_id: Conversation ID to export.
            fmt: Export format string.
        """
        token = self._runner.submit(self._db.get_messages(conv_id))
        self._pending[token] = f"export:{conv_id}:{fmt}"

    def _on_topbar_export(self, fmt: str) -> None:
        """Handle export request from the top bar.

        Args:
            fmt: Export format string.
        """
        conv_id = self._active_conversation_id
        if conv_id:
            self._on_sidebar_export(conv_id, fmt)

    def _on_emily_editor_requested(self) -> None:
        """Open the Emily Editor dialog (system profiles)."""
        from emily_chat.ui.emily_editor import EmilyEditorDialog

        window = self._top_bar.window() if self._top_bar else None
        dlg = EmilyEditorDialog(settings=self._settings, parent=window)
        dlg.exec()

    async def _perform_export(self, conv_id: str, fmt: str, messages: list) -> None:
        """Execute the export pipeline.

        Args:
            conv_id: Conversation ID.
            fmt: Export format.
            messages: List of Message objects.
        """
        from emily_chat.storage.models import ConversationSummary

        conv_result = await self._db.get_conversation(conv_id)
        if conv_result is None:
            return
        await self._export_engine.export(conv_result, messages, fmt)

    def _on_custom_skill_requested(self) -> None:
        """Open the custom skill editor dialog."""
        from emily_chat.ui.skill_editor import SkillEditorDialog

        dlg = SkillEditorDialog(parent=None)
        if dlg.exec():
            skill = dlg.get_skill()
            if skill is not None:
                skill_id = skill.name.lower().replace(" ", "_")
                save_custom_skill(skill_id, skill)
                self._on_skill_changed(skill_id)

    # ── input panel handlers (Phase 15) ────────────────────────

    def _on_slash_command(self, command: str, argument: str) -> None:
        """Dispatch slash commands from the input panel.

        Args:
            command: The command string (e.g. ``"/new"``).
            argument: The argument string after the command.
        """
        if command == "/new":
            self._create_conversation()
        elif command == "/clear":
            self._stream_view.clear_messages()
        elif command == "/model":
            if argument.strip():
                self._settings.default_model = argument.strip()
                self._settings.save()
                if self._top_bar:
                    self._top_bar.set_active_model(argument.strip())
        elif command == "/search":
            self._search(argument)
        elif command == "/export":
            fmt = argument.strip() or "markdown"
            if self._top_bar:
                self._top_bar.export_requested.emit(fmt)
        elif command == "/retry":
            pass
        elif command == "/branch":
            pass
        elif command == "/cost":
            pass
        elif command == "/summarize":
            pass

    def _on_web_search_toggled(self, enabled: bool) -> None:
        """Handle web search toggle.

        Args:
            enabled: Whether web search is now on.
        """
        self._web_search_enabled = enabled

    def _on_quick_skill_override(self, skill_id: str) -> None:
        """Handle a one-message skill override from quick mode.

        Args:
            skill_id: The skill ID to use for the next message only.
        """
        self._one_shot_skill = skill_id if skill_id != "normal" else None

    # ── conversation stream action handlers ─────────────────────

    def _on_edit_message(self, msg_id: str, new_text: str) -> None:
        """Handle a user editing a past message and re-sending.

        Args:
            msg_id: The widget-level message ID.
            new_text: The edited text.
        """
        conv_id = self._active_conversation_id
        if conv_id is not None:
            self._do_send(conv_id, new_text)

    def _on_resend_message(self, msg_id: str) -> None:
        """Handle re-sending a user message as-is.

        Finds the user message widget by *msg_id* and re-sends its text.

        Args:
            msg_id: The widget-level message ID.
        """
        from emily_chat.ui.conversation_stream import UserMessageWidget

        for widget in self._stream_view._messages:
            if isinstance(widget, UserMessageWidget) and widget.msg_id == msg_id:
                text = widget.raw_text
                conv_id = self._active_conversation_id
                if conv_id is not None and text:
                    self._do_send(conv_id, text)
                return

    def _on_retry_message(self, msg_id: str) -> None:
        """Handle retrying an Emily response with the same model.

        Args:
            msg_id: The widget-level message ID.
        """
        pass

    def _on_branch_message(self, msg_id: str) -> None:
        """Handle branching a conversation from a specific message.

        Args:
            msg_id: The widget-level message ID.
        """
        pass

    def _on_feedback(self, msg_id: str, positive: bool) -> None:
        """Handle like/dislike feedback on a message.

        Args:
            msg_id: The widget-level message ID.
            positive: ``True`` for like, ``False`` for dislike.
        """
        pass

    # ── chunk / stream callbacks ────────────────────────────────

    def _on_chunk(self, token: str, chunk: object) -> None:
        """Handle a streaming chunk from the LLM."""
        if not isinstance(chunk, StreamChunk):
            return
        if token != self._active_stream_token:
            return

        if chunk.type == "thinking":
            self._gen_thinking_text += chunk.content
            self._right_panel.append_thinking(chunk.content)

        elif chunk.type == "text":
            self._gen_response_text += chunk.content
            self._stream_view.append_emily_text(chunk.content)

        elif chunk.type == "usage":
            self._gen_usage = dict(chunk.metadata)
            if self._top_bar is not None:
                self._top_bar.set_live_stats(self._gen_usage)

        elif chunk.type == "stop":
            pass  # handled by _on_stream_done

    def _on_stream_done(self, token: str) -> None:
        """Handle stream completion."""
        if token != self._active_stream_token:
            return
        self._active_stream_token = None
        self._finish_generation(stopped=False)

    def _finish_generation(self, stopped: bool = False) -> None:
        """Finalise the generation: update UI, save to DB."""
        self._input_panel.set_generating(False)
        self._right_panel.finish_thinking()

        # Compute thinking duration (approximate from usage timing)
        thinking_seconds: float | None = None
        if self._gen_thinking_text:
            first_tok = self._gen_usage.get("first_token_ms", 0)
            latency = self._gen_usage.get("latency_ms", 0)
            if first_tok and latency:
                thinking_seconds = first_tok / 1000

        self._stream_view.finish_emily_message(
            metadata=self._gen_usage,
            thinking_seconds=thinking_seconds,
        )

        # Use the model spec from the generation, not a fresh lookup
        model_spec = self._gen_model_spec
        if model_spec is None:
            _, model_spec = get_default_model()
        metadata = dict(self._gen_usage)
        metadata["model"] = model_spec.display
        metadata["provider"] = model_spec.provider
        if self._gen_thinking_text:
            metadata["tokens_thinking"] = len(self._gen_thinking_text) // 4
        self._right_panel.set_metadata(metadata)

        # Accumulate session-level stats and update right panel
        self._session_messages.append({
            "model": model_spec.display,
            "tokens_in": self._gen_usage.get("input_tokens", 0),
            "tokens_out": self._gen_usage.get("output_tokens", 0),
            "tokens_thinking": len(self._gen_thinking_text) // 4 if self._gen_thinking_text else 0,
            "cost_usd": self._gen_usage.get("cost_usd", 0.0),
            "latency_ms": self._gen_usage.get("latency_ms", 0),
        })
        session_stats = compute_session_stats(self._session_messages)
        self._right_panel.set_session_stats(session_stats)

        # Append assistant response to in-memory conversation history
        if self._gen_response_text:
            self._conversation_messages.append(
                {"role": "assistant", "content": self._gen_response_text}
            )

        # Save assistant message to DB
        conv_id = self._active_conversation_id
        if conv_id is not None:
            self._runner.submit(
                self._db.add_message(
                    conv_id,
                    "assistant",
                    self._gen_response_text,
                    content_raw=self._gen_response_text,
                    thinking_content=self._gen_thinking_text or None,
                    model=model_spec.model_id,
                    provider=model_spec.provider,
                    tokens_in=self._gen_usage.get("input_tokens", 0),
                    tokens_out=self._gen_usage.get("output_tokens", 0),
                    tokens_thinking=len(self._gen_thinking_text) // 4,
                    cost_usd=self._gen_usage.get("cost_usd", 0.0),
                    latency_ms=self._gen_usage.get("latency_ms"),
                    first_token_ms=self._gen_usage.get("first_token_ms"),
                )
            )
            self._reload_conversations()

        self._input_panel.focus_input()

    # ── result dispatch ─────────────────────────────────────────

    def _on_result(self, token: str, result: Any) -> None:
        """Handle an async result delivered from the background thread."""
        action = self._pending.pop(token, None)

        if action == "init":
            self._reload_conversations()
            token = self._runner.submit(self._discover_ollama_models())
            self._pending[token] = "ollama_discovery"
            token2 = self._runner.submit(self._discover_llamacpp_models())
            self._pending[token2] = "llamacpp_discovery"
            return

        if action == "create":
            if isinstance(result, ConversationSummary):
                self._active_conversation_id = result.id
                self._sidebar.select_conversation(result.id)
                self._settings.last_conversation_id = result.id
                self._settings.save()
                self._stream_view.clear_messages()
                self._conversation_messages = []
            self._reload_conversations()
            return

        if action == "create_then_send":
            if isinstance(result, ConversationSummary):
                self._active_conversation_id = result.id
                self._sidebar.select_conversation(result.id)
                self._settings.last_conversation_id = result.id
                self._settings.save()
                self._stream_view.clear_messages()
                self._conversation_messages = []
                text = getattr(self, "_pending_user_text", "")
                if text:
                    self._do_send(result.id, text)
                    self._pending_user_text = ""  # type: ignore[attr-defined]
            self._reload_conversations()
            return

        if action == "ollama_discovery":
            return
        if action == "llamacpp_discovery":
            return

        if action == "refresh":
            self._reload_conversations()
            return

        if action == "load":
            if isinstance(result, list):
                self._sidebar.populate(
                    result,
                    collapsed_groups=set(self._settings.sidebar_collapsed_groups),
                )
                last = self._settings.last_conversation_id
                if last:
                    self._sidebar.select_conversation(last)
            return

        if action == "load_messages":
            if isinstance(result, list):
                msgs = []
                for m in result:
                    entry: dict[str, Any] = {"role": m.role, "content": m.content}
                    if getattr(m, "thinking_content", None):
                        entry["thinking_content"] = m.thinking_content
                    msgs.append(entry)
                self._stream_view.load_messages(msgs)
                # Sync in-memory conversation history for LLM context
                self._conversation_messages = [
                    {"role": m.role, "content": m.content} for m in result
                ]
            return

        if action == "search":
            pass

        if action and action.startswith("export:"):
            parts = action.split(":", 2)
            if len(parts) == 3 and isinstance(result, list):
                conv_id, fmt = parts[1], parts[2]
                self._runner.submit(self._perform_export(conv_id, fmt, result))

        if action == "overlay_search":
            if isinstance(result, list) and self._search_overlay is not None:
                formatted = [
                    {
                        "conv_id": r.conversation_id,
                        "title": r.title,
                        "excerpt": r.excerpt,
                        "meta": f"rank: {r.match_rank:.1f}",
                    }
                    for r in result
                ]
                self._search_overlay.set_results(formatted)

    def _on_error(self, token: str, tb: str) -> None:
        """Log async errors (future: show toast in UI)."""
        self._pending.pop(token, None)
        if token == self._active_stream_token:
            self._active_stream_token = None
            self._input_panel.set_generating(False)
            self._stream_view.append_emily_text(
                f"\n\n[Error: generation failed]\n"
            )
            self._stream_view.finish_emily_message()
        import sys
        print(f"[ChatController] async error:\n{tb}", file=sys.stderr)

    # ── helpers ─────────────────────────────────────────────────

    def _reload_conversations(self) -> None:
        """Fetch all conversations from the database and repopulate the sidebar."""
        token = self._runner.submit(self._db.get_all_conversations())
        self._pending[token] = "load"
