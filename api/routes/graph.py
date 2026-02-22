"""
Knowledge Graph API routes.

GET /knowledge/graph/entity/{id}      - subgraph around an entity (depth 1-2)
GET /knowledge/graph/path             - shortest path between two entities
GET /knowledge/events                 - list upcoming events
GET /knowledge/proactive/alerts       - run proactive checks and return alerts
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from memory.knowledge_store import KnowledgeStore
from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Dependency placeholders
# ---------------------------------------------------------------------------


def _get_store() -> KnowledgeStore:
    """Placeholder — overridden by app.state dependency injection."""
    raise RuntimeError("KnowledgeStore not wired into API dependencies")


def _get_proactive() -> Any:
    """Placeholder for ProactiveEngine dependency."""
    return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/graph/entity/{entity_id}")
async def entity_subgraph(
    entity_id: str,
    depth: int = Query(default=1, ge=1, le=3),
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """
    Return the relationship subgraph around an entity up to `depth` hops.

    Nodes include entity names. Edges include relationship types and labels.
    Credential nodes are never included.
    """
    entity = await store.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    visited: set[str] = set()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    async def _expand(eid: str, current_depth: int) -> None:
        if eid in visited or current_depth > depth:
            return
        visited.add(eid)

        ent = await store.get_entity(eid)
        if ent:
            nodes.append({
                "id": ent.id,
                "label": ent.canonical_name,
                "type": ent.type,
            })

        rels = await store.get_relationships_for_entity(eid)
        for rel in rels:
            edge = {
                "id": rel.id,
                "from": rel.from_entity_id,
                "to": rel.to_entity_id,
                "type": rel.relationship_type,
                "label": rel.relationship_label or "",
                "strength": rel.strength,
            }
            if edge not in edges:
                edges.append(edge)

            # Expand neighbors
            neighbor_id = rel.to_entity_id if rel.from_entity_id == eid else rel.from_entity_id
            await _expand(neighbor_id, current_depth + 1)

    await _expand(entity_id, 1)

    return {
        "center_entity_id": entity_id,
        "nodes": nodes,
        "edges": edges,
        "depth": depth,
    }


@router.get("/graph/path")
async def entity_path(
    from_id: str = Query(...),
    to_id: str = Query(...),
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """
    Find a shortest relationship path between two entities.

    Uses BFS over the SQLite relationship table. Returns the path as a
    list of nodes and edges.
    """
    # BFS
    from collections import deque

    queue: deque[tuple[str, list[str]]] = deque([(from_id, [from_id])])
    visited: set[str] = {from_id}
    max_depth = 5

    while queue:
        current, path = queue.popleft()
        if len(path) > max_depth:
            break

        rels = await store.get_relationships_for_entity(current)
        for rel in rels:
            neighbor = (
                rel.to_entity_id
                if rel.from_entity_id == current
                else rel.from_entity_id
            )
            if neighbor == to_id:
                full_path = path + [neighbor]
                return {"path": full_path, "hops": len(full_path) - 1}
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))

    return {"path": [], "hops": -1, "message": "No path found within 5 hops"}


@router.get("/events")
async def list_events(
    upcoming_only: bool = Query(default=True),
    limit: int = Query(default=20, le=100),
    store: KnowledgeStore = Depends(_get_store),
) -> dict[str, Any]:
    """List events from the knowledge store."""
    if upcoming_only:
        events = await store.get_upcoming_events(limit=limit)
    else:
        events = await store.get_upcoming_events(limit=limit)  # Extend store if needed

    return {
        "events": [
            {
                "id": e.id,
                "title": e.title,
                "type": e.event_type,
                "datetime": e.datetime,
                "location": e.location,
                "description": e.description,
            }
            for e in events
        ]
    }


@router.get("/proactive/alerts")
async def proactive_alerts(
    proactive: Any = Depends(_get_proactive),
) -> dict[str, Any]:
    """
    Run all proactive checks and return current alerts.

    Credential health alerts are included but contain NO secret material.
    """
    if proactive is None:
        return {"alerts": [], "message": "Proactive engine not configured"}

    try:
        alerts = await proactive.run_all_checks()
        return {
            "alerts": [a.to_dict() for a in alerts],
            "count": len(alerts),
        }
    except Exception as exc:
        log.error("proactive_alerts_api_error", error=str(exc))
        return {"alerts": [], "error": str(exc)}
