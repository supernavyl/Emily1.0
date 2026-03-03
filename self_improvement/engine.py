"""
Self-improvement engine — the unified coordinator for Emily's growth.

Runs during idle cycles to:
1. Analyze performance metrics and detect regressions
2. Surface capability gaps to the ToolBuilderAgent
3. Drive prompt evolution via the PromptEvolver
4. Apply RAG feedback to update retrieval quality scores
5. Prune stale performance logs

The engine is triggered by the Scheduler (P4 Idle priority) when
Emily has been idle for at least `idle_trigger_s` seconds.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from observability.logger import get_logger
from self_improvement.capability_gap_logger import CapabilityGapLogger
from self_improvement.performance_tracker import PerformanceTracker
from self_improvement.prompt_evolver import PromptEvolver
from self_improvement.rag_feedback import RAGFeedbackLoop

log = get_logger(__name__)


class SelfImprovementEngine:
    """
    Orchestrates all self-improvement subsystems.

    Intended to be invoked periodically by the Scheduler during idle time.
    Can also be invoked on-demand by the ReflectionAgent.
    """

    def __init__(self) -> None:
        self.performance = PerformanceTracker()
        self.prompt_evolver = PromptEvolver()
        self.rag_feedback = RAGFeedbackLoop()
        self.gap_logger = CapabilityGapLogger()
        self._last_run: float = 0.0

    async def run_idle_cycle(self) -> dict[str, Any]:
        """
        Execute one full self-improvement idle cycle.

        Returns:
            Summary dict of actions taken.
        """
        log.info("self_improvement_cycle_started")
        t0 = time.monotonic()
        summary: dict[str, Any] = {}

        # 1. Compute performance summaries
        perf_summaries = await asyncio.to_thread(self.performance.get_all_summaries, 24.0)
        summary["performance_categories"] = len(perf_summaries)
        regressions = []
        for s in perf_summaries:
            if s.category == "llm" and s.metric == "latency_ms" and s.p95 > 10_000:
                regressions.append(f"LLM P95 latency: {s.p95:.0f}ms")
            if s.category == "rag" and s.metric == "relevance_score" and s.mean < 0.4:
                regressions.append(f"RAG mean relevance: {s.mean:.2f}")
        summary["regressions"] = regressions

        # 2. Update RAG quality scores
        doc_quality = await asyncio.to_thread(self.rag_feedback.compute_document_quality)
        low_quality_docs = [src for src, q in doc_quality.items() if q < 0.3]
        summary["low_quality_docs"] = low_quality_docs
        if low_quality_docs:
            log.warning("rag_low_quality_documents", count=len(low_quality_docs))

        # 3. Identify top capability gaps
        top_gaps = await asyncio.to_thread(self.gap_logger.get_unresolved, None, 0.5, 5)
        summary["top_gaps"] = [
            {"gap_id": g.gap_id, "type": g.gap_type, "description": g.description[:60]}
            for g in top_gaps
        ]

        # 4. Prune old performance logs
        removed = await asyncio.to_thread(self.performance.prune_old_entries, 30)
        summary["pruned_log_entries"] = removed

        elapsed = (time.monotonic() - t0) * 1000
        summary["elapsed_ms"] = round(elapsed)
        self._last_run = time.time()

        log.info(
            "self_improvement_cycle_complete",
            regressions=len(regressions),
            gaps=len(top_gaps),
            elapsed_ms=summary["elapsed_ms"],
        )
        return summary

    def record_llm_outcome(
        self,
        model_tier: str,
        latency_ms: float,
        critic_score: float,
        prompt_slot: str,
        prompt_version: str,
    ) -> None:
        """
        Record an LLM inference outcome for performance tracking and prompt evolution.

        Args:
            model_tier: LLM tier used ("nano", "fast", "smart", etc.)
            latency_ms: Total inference latency.
            critic_score: CriticAgent quality score (0-1).
            prompt_slot: Prompt slot used (e.g., "system_prompt").
            prompt_version: Prompt version used (e.g., "v1").
        """
        self.performance.record("llm", "latency_ms", latency_ms, {"model_tier": model_tier})
        self.performance.record("llm", "critic_score", critic_score, {"model_tier": model_tier})

        # Feed into prompt evolver
        won = critic_score >= 0.7
        self.prompt_evolver.record_outcome(prompt_slot, prompt_version, critic_score, won=won)

    def record_rag_retrieval(
        self,
        chunk_id: str,
        source: str,
        query: str,
        relevance_score: float,
        used: bool,
    ) -> None:
        """
        Record a RAG retrieval event.

        Args:
            chunk_id: Retrieved chunk ID.
            source: Source document path.
            query: The query that triggered retrieval.
            relevance_score: Retriever's confidence score.
            used: Whether the chunk was cited in the response.
        """
        self.performance.record("rag", "relevance_score", relevance_score, {"source": source})
        self.rag_feedback.record(
            chunk_id=chunk_id,
            document_source=source,
            query=query,
            relevance_score=relevance_score,
            used_in_response=used,
        )

    def log_capability_gap(
        self,
        gap_type: str,
        description: str,
        context: dict | None = None,
    ) -> None:
        """
        Log a capability gap for later resolution.

        Args:
            gap_type: Type of gap.
            description: What Emily couldn't do.
            context: Supporting context.
        """
        self.gap_logger.log_gap(gap_type, description, context)
