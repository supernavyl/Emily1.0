"""
Knowledge graph using networkx for entity relationship tracking.

Entities (people, concepts, projects, tools) are nodes.
Relationships are directed labeled edges.

Graph is serialized to JSON for persistence and loaded at startup.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class KnowledgeGraph:
    """
    In-process networkx knowledge graph for Emily's semantic memory.

    Nodes: entities extracted from conversations and documents.
    Edges: named relationships between entities.

    Supports:
    - Entity and relationship addition
    - Neighbor traversal for RAG context expansion
    - Serialization to/from JSON
    """

    _GRAPH_PATH = "data/knowledge_graph.json"

    def __init__(self) -> None:
        self._graph: object | None = None
        self._available = False

    def load(self) -> None:
        """Initialize or load the knowledge graph."""
        try:
            import networkx as nx  # type: ignore[import-untyped]
            graph_path = Path(self._GRAPH_PATH)
            if graph_path.exists():
                data = json.loads(graph_path.read_text())
                self._graph = nx.node_link_graph(data)
                log.info(
                    "knowledge_graph_loaded",
                    nodes=self._graph.number_of_nodes(),  # type: ignore[union-attr]
                    edges=self._graph.number_of_edges(),  # type: ignore[union-attr]
                )
            else:
                self._graph = nx.DiGraph()
            self._available = True
        except ImportError:
            log.warning("networkx_not_installed_knowledge_graph_disabled")
        except Exception as exc:
            import networkx as nx
            log.error("knowledge_graph_load_error", error=str(exc))
            self._graph = nx.DiGraph()
            self._available = True

    def add_entity(self, name: str, entity_type: str, **attributes: Any) -> None:
        """
        Add an entity node to the graph.

        Args:
            name: Entity name (used as node ID).
            entity_type: Type tag (e.g., "person", "project", "concept").
            **attributes: Additional node attributes.
        """
        if not self._available or self._graph is None:
            return
        self._graph.add_node(  # type: ignore[union-attr]
            name,
            entity_type=entity_type,
            created_at=time.time(),
            **attributes,
        )

    def add_relationship(
        self,
        source: str,
        target: str,
        relationship: str,
        **attributes: Any,
    ) -> None:
        """
        Add a directed relationship edge between two entities.

        Args:
            source: Source entity name.
            target: Target entity name.
            relationship: Relationship label (e.g., "works_on", "knows").
            **attributes: Additional edge attributes.
        """
        if not self._available or self._graph is None:
            return
        # Ensure both nodes exist
        if not self._graph.has_node(source):  # type: ignore[union-attr]
            self.add_entity(source, "unknown")
        if not self._graph.has_node(target):  # type: ignore[union-attr]
            self.add_entity(target, "unknown")
        self._graph.add_edge(  # type: ignore[union-attr]
            source,
            target,
            relationship=relationship,
            created_at=time.time(),
            **attributes,
        )

    def get_neighbors(self, entity: str, depth: int = 1) -> list[dict[str, Any]]:
        """
        Get neighboring entities within N hops.

        Args:
            entity: Starting entity name.
            depth: Number of hops to traverse.

        Returns:
            List of neighbor dicts with name, type, and relationship.
        """
        if not self._available or self._graph is None:
            return []

        import networkx as nx
        neighbors: list[dict[str, Any]] = []
        visited = {entity}

        frontier = [entity]
        for _ in range(depth):
            next_frontier = []
            for node in frontier:
                for _, neighbor, data in self._graph.edges(node, data=True):  # type: ignore[union-attr]
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
                        node_data = self._graph.nodes[neighbor]  # type: ignore[union-attr]
                        neighbors.append({
                            "name": neighbor,
                            "entity_type": node_data.get("entity_type", "unknown"),
                            "relationship": data.get("relationship", "related_to"),
                            "source": node,
                        })
            frontier = next_frontier

        return neighbors

    def search_entities(self, query: str) -> list[str]:
        """
        Find entity names that match a query string.

        Args:
            query: Search string (case-insensitive substring match).

        Returns:
            List of matching entity names.
        """
        if not self._available or self._graph is None:
            return []
        q = query.lower()
        return [n for n in self._graph.nodes() if q in n.lower()]  # type: ignore[union-attr]

    async def save(self) -> None:
        """Persist the graph to disk as JSON."""
        if not self._available or self._graph is None:
            return
        try:
            import networkx as nx
            data = nx.node_link_data(self._graph)
            path = Path(self._GRAPH_PATH)
            path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                path.write_text,
                json.dumps(data, default=str),
            )
            log.debug(
                "knowledge_graph_saved",
                nodes=self._graph.number_of_nodes(),  # type: ignore[union-attr]
                edges=self._graph.number_of_edges(),  # type: ignore[union-attr]
            )
        except Exception as exc:
            log.error("knowledge_graph_save_error", error=str(exc))

    @property
    def is_available(self) -> bool:
        """True if networkx is installed and graph is initialized."""
        return self._available

    def stats(self) -> dict[str, int]:
        """Return graph statistics."""
        if not self._available or self._graph is None:
            return {"nodes": 0, "edges": 0}
        return {
            "nodes": self._graph.number_of_nodes(),  # type: ignore[union-attr]
            "edges": self._graph.number_of_edges(),  # type: ignore[union-attr]
        }
