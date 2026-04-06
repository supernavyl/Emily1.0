"""Tests for FleetAdapter — bridges LLMFleet to emily-loop's LLMClient protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from emily_loop.llm import LLMClient


@dataclass
class FakeCompletionResult:
    content: str
    model: str = "test"
    total_tokens: int = 10
    prompt_tokens: int = 5
    latency_ms: float = 100.0


class FakeFleet:
    """Minimal mock of LLMFleet for adapter tests."""

    def __init__(self) -> None:
        self.chat = AsyncMock()


@pytest.fixture
def fake_fleet() -> FakeFleet:
    return FakeFleet()


@pytest.mark.asyncio
async def test_fleet_adapter_satisfies_protocol(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    adapter = FleetAdapter(fake_fleet)
    assert isinstance(adapter, LLMClient)


@pytest.mark.asyncio
async def test_fleet_adapter_complete_text(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    fake_fleet.chat.return_value = FakeCompletionResult(content="Hello world")
    adapter = FleetAdapter(fake_fleet)

    result = await adapter.complete("Say hello")

    assert result == "Hello world"
    fake_fleet.chat.assert_called_once()


@pytest.mark.asyncio
async def test_fleet_adapter_complete_json_schema(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    fake_fleet.chat.return_value = FakeCompletionResult(
        content=json.dumps({"steps": [{"id": "step-001", "action": "do thing"}]})
    )
    adapter = FleetAdapter(fake_fleet)

    result = await adapter.complete("Generate a plan", schema=dict)

    assert isinstance(result, dict)
    assert "steps" in result


@pytest.mark.asyncio
async def test_fleet_adapter_uses_specified_tier(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter
    from llm.router import ModelTier

    fake_fleet.chat.return_value = FakeCompletionResult(content="fast response")
    adapter = FleetAdapter(fake_fleet, tier=ModelTier.FAST)

    await adapter.complete("Quick question")

    call_kwargs = fake_fleet.chat.call_args
    assert call_kwargs.kwargs.get("force_tier") == ModelTier.FAST


@pytest.mark.asyncio
async def test_fleet_adapter_json_parse_error_raises(fake_fleet: FakeFleet) -> None:
    from core.loop_integration.fleet_adapter import FleetAdapter

    fake_fleet.chat.return_value = FakeCompletionResult(content="not json at all")
    adapter = FleetAdapter(fake_fleet)

    with pytest.raises(json.JSONDecodeError):
        await adapter.complete("Give me JSON", schema=dict)
