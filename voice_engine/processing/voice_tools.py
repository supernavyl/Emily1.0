"""Voice tool orchestrator — routes voice commands to Emily's tool ecosystem.

Sits inside EmilyLLMProvider.stream_response() and intercepts utterances
that look like tool commands (regex pre-filter), classifies them with a
fast 8B LLM call, executes the matching tool, and yields speakable tokens
back into the voice pipeline.

The pipeline, TTS, and conversation controller remain completely unaware
of tools — they just see string tokens.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any

from llm.structured_output import extract_json
from plugins.base import ExecutionContext, ToolResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from llm.fleet import LLMFleet
    from llm.prompt_builder import PromptBuilder
    from plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool categories
# ---------------------------------------------------------------------------

FIRE_AND_FORGET: frozenset[str] = frozenset({
    "computer_open",
    "app_launch",
    "notification_sender",
    "home_assistant",
})

QUERY_AND_SUMMARIZE: frozenset[str] = frozenset({
    "calculator",
    "web_search",
    "web_fetch",
    "system_info",
    "list_windows",
    "list_apps",
    "process_manager",
    "calendar_reader",
    "clipboard",
    "recent_files",
    "computer_search",
})

VOICE_SAFE: frozenset[str] = FIRE_AND_FORGET | QUERY_AND_SUMMARIZE

# ---------------------------------------------------------------------------
# Intent detection regex — generous, false positives are cheap (~300ms)
# ---------------------------------------------------------------------------

_TOOL_TRIGGER_RE = re.compile(
    r"\b(open|launch|start|run|close|quit|exit|kill|stop"
    r"|search\b|look\s+up|google|find"
    r"|calculate|compute|what(?:'s|s|\s+is)\s+\d|how\s+much"
    r"|remind|notification|notify|alert"
    r"|what(?:'s|s)\s+running|which\s+(?:apps|windows)"
    r"|turn\s+(?:on|off)|temperature|lights?|dim|brighten"
    r"|clipboard|copy|paste"
    r"|system\s+info|cpu|ram|memory|disk|battery"
    r"|calendar|schedule|what(?:'s|s)\s+(?:on\s+)?(?:my|today)"
    r"|recent\s+files)\b",
    re.IGNORECASE,
)

# Tool execution timeout
_TOOL_TIMEOUT_S = 15.0

# Voice execution context (no sandbox restrictions for voice tools)
_VOICE_CONTEXT = ExecutionContext(
    session_id="voice",
    user_id="owner",
    sandbox_enabled=False,
)


class VoiceToolOrchestrator:
    """Routes voice commands through Emily's tool ecosystem.

    All tool logic is contained here — the voice pipeline only sees
    yielded string tokens.
    """

    def __init__(
        self,
        fleet: LLMFleet,
        prompt_builder: PromptBuilder,
        registry: PluginRegistry,
    ) -> None:
        self._fleet = fleet
        self._prompt_builder = prompt_builder
        self._registry = registry
        self._voice_schemas: list[dict[str, Any]] | None = None
        logger.info("VoiceToolOrchestrator initialised (%d tools in registry)", len(registry))

    def _get_voice_schemas(self) -> list[dict[str, Any]]:
        """Return condensed schemas for voice-safe tools only (lazy-loaded)."""
        if self._voice_schemas is None:
            self._voice_schemas = []
            for tool in self._registry.all_tools():
                if tool.name in VOICE_SAFE and not tool.requires_approval:
                    self._voice_schemas.append({
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    })
            logger.info(
                "voice_tool_schemas_loaded",
                extra={"count": len(self._voice_schemas)},
            )
        return self._voice_schemas

    def matches_tool_intent(self, text: str) -> bool:
        """Fast regex pre-filter. <0.01ms. False positives are acceptable."""
        return bool(_TOOL_TRIGGER_RE.search(text))

    async def classify_intent(
        self,
        user_text: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        """Classify whether the utterance is a tool command or conversation.

        Uses a non-streaming LLM call with the 8B VOICE_FAST model.

        Returns:
            Dict with "action", "parameters", "acknowledgment" keys,
            or {"action": "conversation"}, or None on failure.
        """
        from llm.client import ChatMessage
        from llm.router import ModelTier

        schemas = self._get_voice_schemas()
        if not schemas:
            return None

        classification_prompt = self._prompt_builder.build_voice_tool_classification_prompt(
            tools=schemas,
            user_text=user_text,
        )

        chat_messages = [
            ChatMessage(role="system", content=classification_prompt),
            ChatMessage(role="user", content=user_text),
        ]

        try:
            result = await self._fleet.chat(
                user_message=user_text,
                messages=chat_messages,
                force_tier=ModelTier.VOICE_FAST,
                max_tokens=200,
                temperature=0.1,
            )
            parsed = extract_json(result.content)
            if parsed is None:
                logger.warning("voice_tool_classify_no_json", extra={"raw": result.content[:200]})
                return None

            action = parsed.get("action", "conversation")
            if action == "conversation":
                return {"action": "conversation"}

            # Validate the tool exists and is voice-safe
            if action not in VOICE_SAFE:
                logger.info("voice_tool_classify_unsafe", extra={"action": action})
                return {"action": "conversation"}

            return parsed

        except Exception as exc:
            logger.error("voice_tool_classify_error", extra={"error": str(exc)[:200]})
            return None

    async def execute_tool(self, name: str, params: dict[str, Any]) -> ToolResult:
        """Look up and execute a tool by name with timeout."""
        tool = self._registry.get(name)
        if tool is None:
            return ToolResult.fail(f"Unknown tool: {name}")

        try:
            return await asyncio.wait_for(
                tool.safe_execute(params, _VOICE_CONTEXT),
                timeout=_TOOL_TIMEOUT_S,
            )
        except TimeoutError:
            return ToolResult.fail(f"Tool '{name}' timed out after {_TOOL_TIMEOUT_S}s")

    async def handle_voice_tool(
        self,
        user_text: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str] | None:
        """Main entry point. Returns None if this is normal conversation.

        Otherwise yields speakable tokens: acknowledgment first, then
        (for query tools) a natural-language summary of the result.
        """
        intent = await self.classify_intent(user_text, messages)
        if intent is None or intent.get("action") == "conversation":
            return None

        action = intent["action"]
        params = intent.get("parameters", {})
        acknowledgment = intent.get("acknowledgment", "On it.")

        return self._tool_stream(user_text, action, params, acknowledgment, messages)

    async def _tool_stream(
        self,
        user_text: str,
        action: str,
        params: dict[str, Any],
        acknowledgment: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """Yield acknowledgment, execute tool, optionally stream summary."""
        # Yield the acknowledgment immediately so TTS can start speaking
        yield acknowledgment

        # Execute the tool
        result = await self.execute_tool(action, params)

        if not result.success:
            error_msg = result.error or "something went wrong"
            yield f" I couldn't do that. {error_msg}"
            return

        # Fire-and-forget tools: acknowledgment is sufficient
        if action in FIRE_AND_FORGET:
            logger.info(
                "voice_tool_fire_and_forget",
                extra={"action": action, "ms": result.execution_time_ms},
            )
            return

        # Query tools: stream a spoken summary of the result
        logger.info(
            "voice_tool_query_complete",
            extra={"action": action, "ms": result.execution_time_ms},
        )

        result_text = str(result.output) if result.output else ""
        if not result_text:
            yield " Done, but there were no results."
            return

        async for token in self._stream_result_summary(
            user_text, action, result_text, messages
        ):
            yield token

    async def _stream_result_summary(
        self,
        user_text: str,
        tool_name: str,
        result_text: str,
        messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        """Stream a spoken summary of tool output via the LLM."""
        from llm.client import ChatMessage
        from llm.router import ModelTier
        from voice_engine.processing.think_filter import strip_think_tags

        summary_prompt = self._prompt_builder.build_voice_tool_result_prompt(
            user_text=user_text,
            tool_name=tool_name,
            result_text=result_text,
        )

        chat_messages = [
            ChatMessage(role="system", content=summary_prompt),
            ChatMessage(role="user", content=user_text),
        ]

        try:
            raw_stream = self._fleet.chat_stream(
                user_message=user_text,
                messages=chat_messages,
                force_tier=ModelTier.VOICE_FAST,
                max_tokens=400,
                temperature=0.3,
            )

            async for token in strip_think_tags(raw_stream):
                yield token

        except Exception as exc:
            logger.error("voice_tool_summary_error", extra={"error": str(exc)[:200]})
            # Truncated fallback: just read back part of the result
            yield f" {result_text[:200]}"
