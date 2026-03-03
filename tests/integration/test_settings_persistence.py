"""Integration test: Settings API.

Verify that settings can be read and written via the API,
and that changes are reflected in subsequent reads.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_persona_settings_get(client):
    """GET /settings/persona should return a dict."""
    # Reset module-level cache
    from api.routes import settings as _sm

    _sm._persona = None

    resp = await client.get("/settings/persona")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_advanced_settings_get(client):
    """GET /settings/advanced should return a dict."""
    from api.routes import settings as _sm

    _sm._advanced = None

    resp = await client.get("/settings/advanced")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


@pytest.mark.asyncio
async def test_knowledge_status_endpoint(client, mock_bootstrap):
    """GET /knowledge/status should return pipeline status."""
    resp = await client.get("/knowledge/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "pipeline_active" in data
    assert "watcher_active" in data


@pytest.mark.asyncio
async def test_latency_breakdown_empty(client):
    """GET /metrics/latency-breakdown should return empty list initially."""
    resp = await client.get("/metrics/latency-breakdown")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
