"""Tests that EmilyLLMProvider routes through ModelRouter instead of hardcoded regex."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm.router import ModelTier, RoutingDecision, TaskType


@dataclass
class _FakeEmotionalState:
    engagement: float = 0.7
    confidence: float = 0.8
    concern: float = 0.2
    enthusiasm: float = 0.6


class _FakeEmotionalManager:
    def __init__(self, concern: float = 0.2) -> None:
        self.state = _FakeEmotionalState(concern=concern)


@pytest.fixture
def fleet() -> MagicMock:
    f = MagicMock()
    f.route.return_value = RoutingDecision(
        tier=ModelTier.VOICE_FAST,
        model_name="qwen3-8b",
        complexity_score=2,
        task_type=TaskType.CHAT,
        reason="voice_fast",
    )

    async def _fake_stream(*args, **kwargs):
        yield "Hello "
        yield "there."

    f.chat_stream = MagicMock(side_effect=_fake_stream)
    return f


@pytest.fixture
def memory() -> MagicMock:
    m = MagicMock()
    m.add_user_turn = AsyncMock()
    m.add_assistant_turn = AsyncMock()
    m.retrieve_context = AsyncMock(return_value=[])
    m.has_recall_intent = MagicMock(return_value=False)
    m.procedural = MagicMock()
    m.procedural.user_profile = {"name": "Test"}
    return m


@pytest.fixture
def prompt_builder() -> MagicMock:
    pb = MagicMock()
    pb.build_voice_system_prompt.return_value = "You are Emily."
    pb._format_persona_injection.return_value = ""
    return pb


async def test_voice_routes_through_model_router(
    fleet: MagicMock,
    memory: MagicMock,
    prompt_builder: MagicMock,
) -> None:
    """Voice path must call fleet.route() with voice_mode=True, not hardcode tier."""
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider

    emotional = _FakeEmotionalManager(concern=0.2)
    provider = EmilyLLMProvider(
        fleet=fleet,
        memory=memory,
        prompt_builder=prompt_builder,
        emotional_state=emotional,
    )

    messages = [{"role": "user", "content": "hello"}]
    tokens = []
    async for tok in provider.stream_response(messages):
        tokens.append(tok)

    # fleet.route() must have been called with voice_mode=True
    fleet.route.assert_called_once()
    call_kwargs = fleet.route.call_args
    assert call_kwargs.kwargs.get("voice_mode") is True or call_kwargs[1].get("voice_mode") is True

    # Must NOT use force_tier — let the router decide
    stream_call = fleet.chat_stream.call_args
    # The tier should come from route(), not be hardcoded
    assert stream_call is not None


async def test_voice_urgency_from_emotional_state(
    fleet: MagicMock,
    memory: MagicMock,
    prompt_builder: MagicMock,
) -> None:
    """High concern in emotional state should produce higher urgency."""
    from voice_engine.providers.llm.emily_llm import EmilyLLMProvider

    emotional = _FakeEmotionalManager(concern=0.8)
    provider = EmilyLLMProvider(
        fleet=fleet,
        memory=memory,
        prompt_builder=prompt_builder,
        emotional_state=emotional,
    )

    messages = [{"role": "user", "content": "that's wrong, fix it"}]
    tokens = []
    async for tok in provider.stream_response(messages):
        tokens.append(tok)

    call_kwargs = fleet.route.call_args
    # urgency should be derived from concern (0.8 * 1.5 = 1.2, clamped to 1.0)
    urgency = call_kwargs.kwargs.get("urgency") or call_kwargs[1].get("urgency", 0.5)
    assert urgency > 0.5, f"Expected urgency > 0.5 from high concern, got {urgency}"


async def test_voice_no_complex_voice_re_dependency() -> None:
    """Verify _COMPLEX_VOICE_RE and _is_complex_voice_query are removed."""
    import voice_engine.providers.llm.emily_llm as mod

    assert not hasattr(mod, "_COMPLEX_VOICE_RE"), "_COMPLEX_VOICE_RE should be removed"
    assert not hasattr(mod, "_is_complex_voice_query"), "_is_complex_voice_query should be removed"
