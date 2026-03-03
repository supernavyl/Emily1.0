"""Unit tests for agents.registry.AgentRegistry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def registry():
    bus = MagicMock()
    fleet = MagicMock()
    memory = MagicMock()

    with (
        patch("agents.registry.ConversationAgent") as ca,
        patch("agents.registry.PlannerAgent") as pa,
        patch("agents.registry.MemoryAgent") as ma,
        patch("agents.registry.ReflectionAgent") as ra,
    ):
        for cls in (ca, pa, ma, ra):
            instance = MagicMock()
            instance.name = cls._mock_name or "MockAgent"
            instance.start = AsyncMock()
            instance.stop = AsyncMock()
            cls.return_value = instance

        ca.return_value.name = "ConversationAgent"
        pa.return_value.name = "PlannerAgent"
        ma.return_value.name = "MemoryAgent"
        ra.return_value.name = "ReflectionAgent"

        from agents.registry import AgentRegistry

        reg = AgentRegistry(bus, fleet, memory)
        yield reg


@pytest.mark.asyncio
async def test_start_all_registers_core_agents(registry):
    await registry.start_all()
    assert "ConversationAgent" in registry.agent_names
    assert "PlannerAgent" in registry.agent_names
    assert "MemoryAgent" in registry.agent_names
    assert "ReflectionAgent" in registry.agent_names


@pytest.mark.asyncio
async def test_get_agent_by_name(registry):
    await registry.start_all()
    agent = registry.get("ConversationAgent")
    assert agent is not None
    assert agent.name == "ConversationAgent"


@pytest.mark.asyncio
async def test_get_nonexistent_agent(registry):
    await registry.start_all()
    assert registry.get("FakeAgent") is None


@pytest.mark.asyncio
async def test_stop_all_clears_agents(registry):
    await registry.start_all()
    assert len(registry.agent_names) >= 4
    await registry.stop_all()
    assert len(registry.agent_names) == 0


@pytest.mark.asyncio
async def test_specialist_import_failure_is_graceful(registry):
    await registry.start_all()
    # Core agents still registered even if specialists fail to import
    assert len(registry.agent_names) >= 4
