"""
Knowledge Query API routes.

POST /knowledge/query  - natural-language query across all memory layers

The response context_text is safe for LLM consumption and display.
Credential secrets are NEVER included in query responses.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from memory.query_engine import MemoryQueryEngine, QueryResult
from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Dependency placeholder
# ---------------------------------------------------------------------------


def _get_query_engine() -> MemoryQueryEngine:
    """Placeholder — overridden by app.state dependency injection."""
    raise RuntimeError("MemoryQueryEngine not wired into API dependencies")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """A natural-language knowledge query."""

    query: str
    include_vault: bool = False


class QueryResponse(BaseModel):
    """Safe query response — never contains credential secrets."""

    query: str
    intent: str
    context_text: str
    entities_found: list[dict[str, Any]]
    facts_found: list[dict[str, Any]]
    events_found: list[dict[str, Any]]
    relationships_found: list[dict[str, Any]]
    vault_summaries: list[dict[str, Any]]
    requires_vault_unlock: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/query")
async def knowledge_query(
    body: QueryRequest,
    engine: MemoryQueryEngine = Depends(_get_query_engine),
) -> QueryResponse:
    """
    Execute a natural-language query against all knowledge layers.

    Returns structured results and an LLM-safe context string.
    Credential secrets are never included — only metadata summaries.
    """
    try:
        result: QueryResult = await engine.query(body.query)
    except Exception as exc:
        log.error("knowledge_query_error", error=str(exc))
        raise HTTPException(status_code=500, detail="Query failed") from exc

    return QueryResponse(
        query=result.query,
        intent=result.intent,
        context_text=result.context_text,
        entities_found=result.entities_found,
        facts_found=result.facts_found,
        events_found=result.events_found,
        relationships_found=result.relationships_found,
        vault_summaries=result.vault_summaries,
        requires_vault_unlock=result.requires_vault_unlock,
    )
