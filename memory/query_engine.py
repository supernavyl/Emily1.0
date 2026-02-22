"""
Unified Memory Query Engine — routes natural-language queries across all
knowledge layers and assembles a fused result.

Routing logic:
  1. Classify query intent using the fast LLM (via prompt_builder).
  2. Route to one or more layers in parallel:
       - SQLite KnowledgeStore  (structured entity/fact/event search)
       - Qdrant knowledge collections (semantic search)
       - NetworkX graph (relationship traversal)
       - CredentialVault  (metadata only — never secrets in results)
  3. Fuse results using Reciprocal Rank Fusion (RRF).
  4. Assemble an LLM-readable context string.

Credential queries: vault metadata (name, service, username) is included
in results. The plaintext secret is NEVER included in QueryResult — the
caller must call vault.get() explicitly for that, and MUST NOT pass the
result to TTS or LLM context.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Any

from llm.client import ChatMessage, OllamaClient
from llm.prompt_builder import PromptBuilder
from memory.knowledge_store import KnowledgeStore
from observability.logger import get_logger

log = get_logger(__name__)

_PROMPT_BUILDER = PromptBuilder()

# RRF constant (k=60 is standard)
_RRF_K = 60


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """
    Aggregated result from a multi-layer knowledge query.

    The `context_text` field is safe to send to the LLM — it contains
    no credential secrets.
    """

    query: str
    intent: str
    entities_found: list[dict[str, Any]] = field(default_factory=list)
    facts_found: list[dict[str, Any]] = field(default_factory=list)
    events_found: list[dict[str, Any]] = field(default_factory=list)
    relationships_found: list[dict[str, Any]] = field(default_factory=list)
    vault_summaries: list[dict[str, Any]] = field(default_factory=list)
    semantic_hits: list[dict[str, Any]] = field(default_factory=list)
    context_text: str = ""
    requires_vault_unlock: bool = False


# ---------------------------------------------------------------------------
# Query classifier
# ---------------------------------------------------------------------------


def _extract_json_object(raw: str) -> dict[str, Any]:
    """
    Extract first JSON object from raw LLM text.

    Args:
        raw: Raw LLM response.

    Returns:
        Parsed dict or empty dict on failure.
    """
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {}


class QueryClassifier:
    """
    Classifies a natural-language query into intent + entity hints.

    Calls the nano LLM tier (fast, cheap) for query routing. Falls back
    to "general_search" intent if classification fails.
    """

    def __init__(self, llm_client: OllamaClient, nano_model: str = "phi3:mini") -> None:
        """
        Args:
            llm_client: Shared Ollama client.
            nano_model: Lightweight model to use for query classification.
        """
        self._llm = llm_client
        self._model = nano_model

    async def classify(self, query: str) -> dict[str, Any]:
        """
        Classify a query and extract routing hints.

        Args:
            query: Natural-language query string.

        Returns:
            Dict with keys: intent, entities_mentioned, time_filter,
            entity_type_filter, requires_vault.
        """
        prompt = _PROMPT_BUILDER.build_query_classification_prompt(query)
        messages = [ChatMessage(role="user", content=prompt)]

        try:
            result = await self._llm.chat(
                model=self._model,
                messages=messages,
                temperature=0.0,
                max_tokens=256,
                model_tier="nano",
            )
            parsed = _extract_json_object(result.content)
        except Exception as exc:
            log.warning("query_classification_failed", error=str(exc))
            parsed = {}

        return {
            "intent": parsed.get("intent", "general_search"),
            "entities_mentioned": parsed.get("entities_mentioned", []),
            "time_filter": parsed.get("time_filter"),
            "entity_type_filter": parsed.get("entity_type_filter"),
            "requires_vault": parsed.get("requires_vault", False),
        }


# ---------------------------------------------------------------------------
# RRF Fusion
# ---------------------------------------------------------------------------


def _rrf_fuse(ranked_lists: list[list[str]], k: int = _RRF_K) -> list[str]:
    """
    Reciprocal Rank Fusion over multiple ranked result lists.

    Each list is a ranked sequence of item IDs. Returns a fused ranking.

    Args:
        ranked_lists: List of ranked ID lists (best first in each list).
        k: RRF smoothing constant.

    Returns:
        Fused ranked list of IDs (best first).
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


# ---------------------------------------------------------------------------
# Main query engine
# ---------------------------------------------------------------------------


class MemoryQueryEngine:
    """
    Routes natural-language queries across all knowledge layers and fuses results.

    Usage::

        engine = MemoryQueryEngine(llm_client, knowledge_store)
        result = await engine.query("What do I know about Alice?")
        # result.context_text is safe to send to the main LLM
        # result.requires_vault_unlock == True if a credential query was detected
    """

    def __init__(
        self,
        llm_client: OllamaClient,
        knowledge_store: KnowledgeStore,
        vault: Any | None = None,          # CredentialVault, optional
        vector_store: Any | None = None,   # KnowledgeVectorStore, optional
        graph_store: Any | None = None,    # NetworkX GraphStore, optional
        nano_model: str = "phi3:mini",
    ) -> None:
        """
        Args:
            llm_client: Shared Ollama async client.
            knowledge_store: Connected KnowledgeStore.
            vault: Optional CredentialVault (used for metadata-only searches).
            vector_store: Optional KnowledgeVectorStore for semantic search.
            graph_store: Optional graph store for relationship traversal.
            nano_model: Model to use for query classification.
        """
        self._store = knowledge_store
        self._vault = vault
        self._vectors = vector_store
        self._graph = graph_store
        self._classifier = QueryClassifier(llm_client, nano_model)

    async def query(
        self,
        natural_language_query: str,
        embedding: list[float] | None = None,
    ) -> QueryResult:
        """
        Execute a natural-language query against all knowledge layers.

        Args:
            natural_language_query: The user's question.
            embedding: Optional pre-computed query embedding for vector search.

        Returns:
            QueryResult with fused results and a safe LLM context string.
        """
        result = QueryResult(query=natural_language_query, intent="general_search")

        # ── Step 1: Classify intent ───────────────────────────────────────
        classification = await self._classifier.classify(natural_language_query)
        result.intent = classification["intent"]
        result.requires_vault_unlock = bool(classification.get("requires_vault"))
        entity_hints: list[str] = classification.get("entities_mentioned", [])

        log.info(
            "query_classified",
            intent=result.intent,
            entities=entity_hints,
            vault=result.requires_vault_unlock,
        )

        # ── Step 2: Parallel layer queries ────────────────────────────────
        sql_task = self._query_sql(entity_hints, classification)
        vault_task = self._query_vault(natural_language_query, result.requires_vault_unlock)

        sql_results, vault_results = await asyncio.gather(sql_task, vault_task)

        result.entities_found = sql_results.get("entities", [])
        result.facts_found = sql_results.get("facts", [])
        result.events_found = sql_results.get("events", [])
        result.relationships_found = sql_results.get("relationships", [])
        result.vault_summaries = vault_results

        # ── Step 3: Semantic vector search ────────────────────────────────
        if embedding and self._vectors and self._vectors.is_available:
            result.semantic_hits = await self._query_vectors(embedding, entity_hints)

        # ── Step 4: Assemble LLM-safe context ────────────────────────────
        result.context_text = self._assemble_context(result)

        return result

    async def _query_sql(
        self,
        entity_hints: list[str],
        classification: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Query the SQLite knowledge store based on classification.

        Args:
            entity_hints: Entity names extracted from the query.
            classification: Full classification dict.

        Returns:
            Dict with keys: entities, facts, events, relationships.
        """
        out: dict[str, list[dict[str, Any]]] = {
            "entities": [], "facts": [], "events": [], "relationships": []
        }

        intent = classification.get("intent", "general_search")

        # Find matching entities for all name hints
        all_entities = []
        for hint in entity_hints:
            found = await self._store.find_entities(hint, limit=5)
            all_entities.extend(found)

        # Deduplicate by id
        seen = set()
        unique_entities = []
        for e in all_entities:
            if e.id not in seen:
                seen.add(e.id)
                unique_entities.append(e)

        out["entities"] = [
            {"id": e.id, "name": e.canonical_name, "type": e.type}
            for e in unique_entities
        ]

        # Pull facts and relationships for found entities
        for entity in unique_entities:
            facts = await self._store.get_facts_for_entity(entity.id)
            out["facts"].extend([
                {
                    "entity_id": f.entity_id,
                    "entity_name": entity.canonical_name,
                    "type": f.fact_type,
                    "text": f.fact_text,
                    "confidence": f.confidence,
                }
                for f in facts
            ])

            if intent in ("relationship_query", "general_search"):
                rels = await self._store.get_relationships_for_entity(entity.id)
                out["relationships"].extend([
                    {
                        "from": r.from_entity_id,
                        "to": r.to_entity_id,
                        "type": r.relationship_type,
                        "label": r.relationship_label,
                    }
                    for r in rels
                ])

            if intent in ("event_query", "general_search"):
                events = await self._store.get_events_for_entity(entity.id, limit=5)
                out["events"].extend([
                    {
                        "id": ev.id,
                        "title": ev.title,
                        "datetime": ev.datetime,
                        "type": ev.event_type,
                    }
                    for ev in events
                ])

        # Fallback: birthday / upcoming event queries
        if intent == "event_query" and not unique_entities:
            upcoming = await self._store.get_upcoming_events(limit=5)
            out["events"] = [
                {"id": ev.id, "title": ev.title, "datetime": ev.datetime}
                for ev in upcoming
            ]

        return out

    async def _query_vault(
        self,
        query: str,
        requires_vault: bool,
    ) -> list[dict[str, Any]]:
        """
        Search the vault for matching credentials (summaries only — no secrets).

        Returns an empty list if the vault is not available or locked,
        or if requires_vault is False.

        Args:
            query: Search query string.
            requires_vault: Only search if the classifier flagged this.

        Returns:
            List of credential summary dicts (no secret fields).
        """
        if not requires_vault or self._vault is None:
            return []

        if not self._vault.is_unlocked():
            log.info("vault_query_skipped_locked")
            return [{"__vault_locked": True}]

        try:
            summaries = await self._vault.search(query)
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "service": s.service,
                    "username": s.username,
                    "type": s.type.value,
                    "__note": "secret not included — call vault.get() separately",
                }
                for s in summaries
            ]
        except Exception as exc:
            log.error("vault_query_error", error=str(exc))
            return []

    async def _query_vectors(
        self,
        embedding: list[float],
        entity_hints: list[str],
    ) -> list[dict[str, Any]]:
        """
        Semantic search across knowledge vector collections.

        Args:
            embedding: Query embedding vector.
            entity_hints: Entity names to guide entity_id filtering.

        Returns:
            Fused list of semantic hits.
        """
        if self._vectors is None:
            return []

        # Search all three knowledge collections in parallel
        entity_task = self._vectors.search(embedding, "entity", top_k=5)
        fact_task = self._vectors.search(embedding, "fact", top_k=10)
        event_task = self._vectors.search(embedding, "event", top_k=5)

        entity_hits, fact_hits, event_hits = await asyncio.gather(
            entity_task, fact_task, event_task
        )

        # RRF fusion
        def ids(hits: list[dict]) -> list[str]:
            return [h["id"] for h in hits]

        fused_ids = _rrf_fuse([ids(entity_hits), ids(fact_hits), ids(event_hits)])

        # Rebuild results preserving original hit data
        hit_map = {h["id"]: h for h in entity_hits + fact_hits + event_hits}
        return [hit_map[hid] for hid in fused_ids if hid in hit_map]

    def _assemble_context(self, result: QueryResult) -> str:
        """
        Build a concise, LLM-safe context string from a QueryResult.

        Credential secrets are NEVER included. Vault results appear only
        as service names and usernames.

        Args:
            result: Populated QueryResult.

        Returns:
            Formatted context string for the main LLM.
        """
        lines: list[str] = [f"<knowledge_context query={result.query!r}>"]

        if result.entities_found:
            lines.append("\nENTITIES:")
            for e in result.entities_found[:5]:
                lines.append(f"  • {e['name']} ({e['type']})")

        if result.facts_found:
            lines.append("\nFACTS:")
            for f in result.facts_found[:10]:
                lines.append(f"  • [{f.get('entity_name', '?')}] {f['text']}")

        if result.relationships_found:
            lines.append("\nRELATIONSHIPS:")
            for r in result.relationships_found[:6]:
                lines.append(
                    f"  • {r['from']} —[{r['type']}]→ {r['to']}"
                    + (f" ({r['label']})" if r.get("label") else "")
                )

        if result.events_found:
            lines.append("\nEVENTS:")
            for ev in result.events_found[:5]:
                lines.append(f"  • {ev.get('datetime', '?')} — {ev.get('title', '?')}")

        if result.vault_summaries:
            lines.append("\nCREDENTIALS (metadata only — secrets not shown):")
            for s in result.vault_summaries:
                if "__vault_locked" in s:
                    lines.append("  • [Vault is locked — unlock to access credentials]")
                else:
                    lines.append(f"  • {s['name']} ({s['service']}) — {s['username']}")

        if result.semantic_hits:
            lines.append("\nSEMANTIC MATCHES:")
            for h in result.semantic_hits[:5]:
                lines.append(f"  • {h.get('text', '')[:120]}")

        lines.append("</knowledge_context>")
        return "\n".join(lines)
