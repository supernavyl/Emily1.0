"""Full multi-provider streaming chat for the React frontend.

Uses :class:`~emily_chat.models.streaming_engine.StreamingEngine` and
the full provider registry to serve SSE-streamed responses with thinking,
usage metadata, cost tracking, and tool/plugin execution.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["chat"])

# Maximum tool-call rounds per message to prevent infinite loops
_MAX_TOOL_ROUNDS = 5

# Module-level lazy registry so builtins are only loaded once
_plugin_registry: Any = None


def _get_registry() -> Any:
    """Return the shared PluginRegistry, loading builtins on first call."""
    global _plugin_registry
    if _plugin_registry is None:
        from plugins.registry import PluginRegistry

        _plugin_registry = PluginRegistry()
        _plugin_registry.load_builtins()
    return _plugin_registry


def _build_tool_schemas() -> list[dict]:
    """Return Ollama-format tool schemas for all currently enabled tools."""
    try:
        from api.routes.settings import is_tool_enabled

        registry = _get_registry()
        schemas = []
        for raw in registry.all_schemas():
            if not is_tool_enabled(raw["name"]):
                continue
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": raw["name"],
                        "description": raw.get("description", ""),
                        "parameters": raw.get(
                            "parameters",
                            {
                                "type": "object",
                                "properties": {},
                            },
                        ),
                    },
                }
            )
        return schemas
    except Exception:
        return []


class ChatStreamRequest(BaseModel):
    """Incoming request for the streaming chat endpoint."""

    message: str
    conversation_id: str | None = None
    model_id: str = "auto"
    skill_id: str = "normal"
    mode_id: str = "normal"
    profile_id: str = "default"
    messages: list[dict[str, str]] = Field(default_factory=list)
    temperature: float | None = None
    web_search: bool = False


def _get_search_url() -> str:
    """Return the configured SearXNG URL."""
    try:
        from config import load_config

        cfg = load_config()
        return cfg.get("tools", {}).get("web_search_url", "http://localhost:8888")
    except Exception:
        return "http://localhost:8888"


def _sse_event(event: str, data: dict[str, Any]) -> str:
    """Format an SSE event line pair."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream")
async def chat_stream(req: ChatStreamRequest) -> StreamingResponse:
    """SSE streaming chat with full multi-provider support, modes, reasoning, and tool execution."""
    from emily_chat.emily.persona import (
        EmilyPersonaEngine,
        PrivacyGrants,
        SessionContext,
    )
    from emily_chat.emily.skills import EMILY_SKILLS, get_skill
    from emily_chat.models.auto_router import EmilyAutoRouter, RoutingRequest
    from emily_chat.models.cost_tracker import estimate_cost
    from emily_chat.models.registry import ModelSpec, get_model
    from emily_chat.models.streaming_engine import (
        GenerationSettings,
        StreamingEngine,
    )
    from emily_chat.profiles import load_profiles, resolve_model_for_skill
    from modes.registry import get_mode
    from plugins.base import ExecutionContext
    from rules.evaluator import RuleEvaluator

    # ── Load mode + skill ────────────────────────────────────────
    mode = get_mode(req.mode_id)
    skill = get_skill(req.skill_id)
    if skill is None:
        skill = EMILY_SKILLS.get("normal") or next(iter(EMILY_SKILLS.values()))

    # ── Evaluate pre_response rules ──────────────────────────────
    rule_evaluator = RuleEvaluator()
    pre_actions = rule_evaluator.evaluate(
        "pre_response",
        mode_id=req.mode_id,
        skill_id=req.skill_id,
        user_text=req.message,
    )
    # Check for blocking rules
    for action in pre_actions:
        if action.action == "block":

            async def blocked_response(
                _payload: str = action.payload,
            ) -> AsyncIterator[str]:
                yield _sse_event(
                    "meta",
                    {
                        "model_key": "blocked",
                        "model_id": "",
                        "provider": "rules",
                        "display": "Blocked by rule",
                    },
                )
                yield _sse_event("text", {"text": _payload})
                yield _sse_event("done", {})

            return StreamingResponse(
                blocked_response(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    model_key: str = req.model_id
    model_spec: ModelSpec | None = None

    if model_key == "auto":
        model_key = resolve_model_for_skill(
            load_profiles(),
            req.profile_id,
            req.skill_id,
            "auto",
        )

    if model_key == "auto":
        auto_router = EmilyAutoRouter()
        routing_req = RoutingRequest(
            text=req.message,
            thinking_enabled=skill.enable_thinking or mode.enable_thinking,
        )
        model_spec = auto_router.route(routing_req)

    if model_spec is None:
        model_spec = get_model(model_key)
    if model_spec is None:
        raise HTTPException(400, f"Unknown model: {model_key}")

    # ── Apply mode overrides ─────────────────────────────────────
    # Check for tier override rules
    for action in pre_actions:
        if action.action == "modify_tier":
            override_spec = get_model(f"emily-{action.payload}")
            if override_spec:
                model_spec = override_spec

    persona = EmilyPersonaEngine()

    # Build system prompt with mode context
    system_prompt: str = persona.build_system_prompt(
        skill=skill,
        privacy_grants=PrivacyGrants(),
        session_context=SessionContext(
            provider_name=model_spec.provider,
        ),
    )

    # Inject rule prompts (inject_prompt actions)
    for action in pre_actions:
        if action.action == "inject_prompt":
            system_prompt += f"\n\n{action.payload}"

    # Mode context injection
    if req.mode_id != "normal":
        system_prompt += (
            f"\n\n━━ ACTIVE MODE: {mode.display} ━━\n"
            f"{mode.description}\n"
            f"Strategy: {mode.reasoning_strategy}\n"
            f"━━━━━━━━━━━━━━━━━━━━━"
        )

    temp = (
        req.temperature
        if req.temperature is not None
        else mode.temperature_override
        if mode.temperature_override is not None
        else skill.temperature
    )
    thinking_budget = (
        8000 if (skill.enable_thinking or mode.enable_thinking) and model_spec.thinking else 0
    )

    # Load tool schemas for Ollama tool calling (only for Ollama provider)
    tool_schemas = _build_tool_schemas() if model_spec.provider == "ollama" else []

    loop_messages: list[dict] = [dict(m) for m in req.messages]
    if not loop_messages or loop_messages[-1].get("content") != req.message:
        loop_messages.append({"role": "user", "content": req.message})

    exec_ctx = ExecutionContext(
        session_id=req.conversation_id or "web-chat",
        sandbox_enabled=True,
    )

    async def generate() -> AsyncIterator[str]:
        yield _sse_event(
            "meta",
            {
                "model_key": model_key,
                "model_id": model_spec.model_id,
                "provider": model_spec.provider,
                "display": model_spec.display,
                "mode_id": req.mode_id,
                "mode_display": mode.display,
                "mode_icon": mode.icon,
                "reasoning_strategy": mode.reasoning_strategy,
            },
        )

        # ── Pre-search: if user toggled Globe, search before LLM call ──
        search_context = ""
        if req.web_search:
            yield _sse_event("search", {"status": "searching", "query": req.message})
            try:
                from plugins.builtin.web_fetch import WebFetchTool
                from plugins.builtin.web_search import WebSearchTool

                searcher = WebSearchTool(searxng_url=_get_search_url())
                fetcher = WebFetchTool()

                search_result = await searcher.execute(
                    {"query": req.message, "num_results": 5},
                    exec_ctx,
                )
                sources: list[dict[str, str]] = []
                if search_result.success:
                    results = search_result.output or []
                    yield _sse_event(
                        "search",
                        {
                            "status": "found",
                            "count": len(results),
                            "results": [{"title": r["title"], "url": r["url"]} for r in results],
                        },
                    )

                    fetched = []
                    for r in results[:3]:
                        yield _sse_event(
                            "search", {"status": "reading", "url": r["url"], "title": r["title"]}
                        )
                        fetch_result = await fetcher.execute(
                            {"url": r["url"], "max_chars": 4000},
                            exec_ctx,
                        )
                        if fetch_result.success:
                            fetched.append(
                                {
                                    "title": r["title"],
                                    "url": r["url"],
                                    "content": str(fetch_result.output)[:3000],
                                }
                            )
                            sources.append({"title": r["title"], "url": r["url"]})

                    if fetched:
                        ctx_parts = []
                        for i, f in enumerate(fetched, 1):
                            ctx_parts.append(
                                f"[{i}] {f['title']}\nSource: {f['url']}\n{f['content']}"
                            )
                        search_context = (
                            "<web_search_results>\n"
                            + "\n\n".join(ctx_parts)
                            + "\n</web_search_results>"
                        )

                    yield _sse_event("search", {"status": "done", "sources": sources})

            except Exception as exc:
                yield _sse_event("search", {"status": "error", "message": str(exc)[:300]})

        if search_context:
            loop_messages[-1]["content"] = (
                search_context + "\n\nUser question: " + loop_messages[-1]["content"]
            )

        engine = StreamingEngine()
        t0 = time.monotonic()
        tokens_in = 0
        tokens_out = 0
        tokens_thinking = 0

        # Agentic tool loop — repeats if model calls tools
        current_tool_schemas = list(tool_schemas)
        for _round in range(_MAX_TOOL_ROUNDS):
            settings = GenerationSettings(
                temperature=temp,
                thinking_budget=thinking_budget,
                tools=current_tool_schemas,
            )

            pending_tool_calls: list[dict] = []

            try:
                async for chunk in engine.stream(
                    model_spec,
                    loop_messages,
                    system_prompt,
                    settings,
                    persona_filter=persona.filter_response_chunk,
                ):
                    if chunk.type == "thinking":
                        yield _sse_event("thinking", {"text": chunk.content})

                    elif chunk.type == "text":
                        yield _sse_event("text", {"text": chunk.content})

                    elif chunk.type == "tool_call":
                        pending_tool_calls = chunk.metadata.get("tool_calls", [])

                    elif chunk.type == "usage":
                        usage = chunk.metadata or {}
                        tokens_in += usage.get(
                            "input_tokens",
                            usage.get("prompt_tokens", 0),
                        )
                        tokens_out += usage.get(
                            "output_tokens",
                            usage.get("completion_tokens", 0),
                        )
                        tokens_thinking += usage.get("reasoning_tokens", 0)

                    elif chunk.type == "error":
                        yield _sse_event("error", {"message": chunk.content})
                        return

                    elif chunk.type == "stop":
                        break

            except Exception as exc:
                yield _sse_event("error", {"message": str(exc)[:500]})
                return

            # No tool calls → generation is complete
            if not pending_tool_calls:
                break

            # Execute each tool call and build tool result messages
            registry = _get_registry()
            assistant_tool_msg: dict = {
                "role": "assistant",
                "content": "",
                "tool_calls": pending_tool_calls,
            }
            loop_messages.append(assistant_tool_msg)

            for call in pending_tool_calls:
                fn = call.get("function", {})
                tool_name: str = fn.get("name", "")
                tool_args = fn.get("arguments", {})
                if isinstance(tool_args, str):
                    try:
                        tool_args = json.loads(tool_args)
                    except json.JSONDecodeError:
                        tool_args = {}

                yield _sse_event(
                    "tool_call",
                    {
                        "name": tool_name,
                        "args": tool_args,
                    },
                )

                tool = registry.get(tool_name)
                if tool is not None:
                    result = await tool.safe_execute(tool_args, exec_ctx)
                    result_text = str(result.output) if result.success else f"Error: {result.error}"
                else:
                    result_text = f"Tool '{tool_name}' is not available."

                yield _sse_event(
                    "tool_result",
                    {
                        "name": tool_name,
                        "result": result_text[:4000],
                        "success": tool is not None and result.success if tool else False,
                    },
                )
                loop_messages.append({"role": "tool", "content": result_text})

            # After tool results, remove tools from the next round's settings
            # to encourage a final answer rather than more tool calls
            current_tool_schemas = []

        latency_ms = int((time.monotonic() - t0) * 1000)
        cost = estimate_cost(model_spec, tokens_in, tokens_out, tokens_thinking)

        yield _sse_event(
            "usage",
            {
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "tokens_thinking": tokens_thinking,
                "cost_usd": cost,
                "latency_ms": latency_ms,
                "model_key": model_key,
                "provider": model_spec.provider,
                "mode_id": req.mode_id,
                "reasoning_strategy": mode.reasoning_strategy,
            },
        )

        if req.conversation_id:
            try:
                from api.app import get_chat_db

                db = get_chat_db()
                if db:
                    await db.add_message(req.conversation_id, "user", req.message)
            except Exception:
                pass

        yield _sse_event("done", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
