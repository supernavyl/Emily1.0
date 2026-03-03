"""Shared fixtures for integration tests.

Uses httpx.AsyncClient with the in-process FastAPI app so no real
server is needed.  All external backends (Ollama, Qdrant) are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# In-process ASGI test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def client():
    """Yield an httpx.AsyncClient backed by Emily's FastAPI app."""
    import httpx

    from api.app import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


@pytest.fixture()
def mock_bootstrap():
    """Patch _bootstrap in api.app with a minimal mock."""
    from api import app as app_module

    bootstrap = MagicMock()
    bootstrap.fleet = MagicMock()
    bootstrap.memory = MagicMock()
    bootstrap.ingestor = None
    bootstrap.rag_watcher = None
    bootstrap.self_improvement = MagicMock()

    original = app_module._bootstrap
    app_module._bootstrap = bootstrap
    yield bootstrap
    app_module._bootstrap = original
