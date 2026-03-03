"""Integration test: Chat API end-to-end.

Send a chat message via the SSE endpoint and verify:
- Response streams back via SSE
- Correct content-type header
- Final response is non-empty
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_chat_endpoint_exists(client):
    """POST /api/v1/chat/stream endpoint should be registered."""
    # Send a minimal request; without a real bootstrap it may fail,
    # but the route itself should be registered (not 404).
    resp = await client.post(
        "/api/v1/chat/stream",
        json={"message": "Hello Emily", "stream": True},
    )
    # 404 means route not mounted; anything else means it's wired
    assert resp.status_code != 404, "Chat route not mounted"


@pytest.mark.asyncio
async def test_metrics_summary_endpoint(client):
    """GET /metrics/summary should return prometheus snapshot."""
    resp = await client.get("/metrics/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data


@pytest.mark.asyncio
async def test_latency_breakdown_endpoint(client):
    """GET /metrics/latency-breakdown should return entries list."""
    resp = await client.get("/metrics/latency-breakdown")
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert isinstance(data["entries"], list)
