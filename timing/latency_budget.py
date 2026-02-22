"""
Latency budget enforcer for Emily's voice pipeline.

Wraps every pipeline stage with a timeout. If any stage exceeds its
budget, a graceful fallback is used instead of blocking the pipeline.

Budget violations are logged at WARNING level and tracked as metrics.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypeVar

from observability.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T")


@dataclass
class StageBudget:
    """Budget definition for a single pipeline stage."""

    name: str
    budget_ms: float
    fallback_value: Any = None
    fallback_description: str = "skip"


_DEFAULT_BUDGETS: dict[str, StageBudget] = {
    "aec_noise": StageBudget("aec_noise", 5.0, None, "skip noise suppression"),
    "vad": StageBudget("vad", 5.0, 0.5, "use raw speech probability"),
    "speaker_id": StageBudget("speaker_id", 20.0, "unknown", "label as unknown"),
    "turn_detection": StageBudget("turn_detection", 10.0, None, "use silence-only"),
    "stt_commit": StageBudget("stt_commit", 50.0, None, "use partial hypothesis"),
    "filler_start": StageBudget("filler_start", 50.0, None, "skip filler"),
    "llm_first_token": StageBudget("llm_first_token", 300.0, None, "use fast model"),
    "tts_first_chunk": StageBudget("tts_first_chunk", 100.0, None, "use kokoro fallback"),
    "audio_output": StageBudget("audio_output", 10.0, None, "direct buffer flush"),
}


@dataclass
class LatencyRecord:
    """A single latency measurement."""

    stage: str
    latency_ms: float
    exceeded: bool
    timestamp: float = field(default_factory=time.monotonic)


class LatencyBudget:
    """
    Enforces hard latency targets at every pipeline stage.

    If any stage exceeds its budget: log warning + return fallback.
    Three consecutive violations in 60s disable the stage for 30s.
    """

    _VIOLATION_WINDOW_S = 60.0
    _DISABLE_DURATION_S = 30.0
    _VIOLATION_THRESHOLD = 3

    def __init__(self) -> None:
        self._budgets: dict[str, StageBudget] = dict(_DEFAULT_BUDGETS)
        self._records: dict[str, list[LatencyRecord]] = {}
        self._violation_counts: dict[str, list[float]] = {}
        self._disabled_until: dict[str, float] = {}

    def set_budget(self, name: str, budget_ms: float, fallback: Any = None) -> None:
        """
        Set or update a stage budget.

        Args:
            name: Stage name.
            budget_ms: Maximum allowed latency in milliseconds.
            fallback: Value to return when budget is exceeded.
        """
        self._budgets[name] = StageBudget(name, budget_ms, fallback)

    async def check_stage(
        self,
        stage: str,
        coro: Coroutine[Any, Any, T],
    ) -> T | Any:
        """
        Run a coroutine with budget enforcement.

        Args:
            stage: Stage name (must match a registered budget).
            coro: The coroutine to time-bound.

        Returns:
            The coroutine result, or the fallback value if budget exceeded.
        """
        budget = self._budgets.get(stage)
        if budget is None:
            return await coro

        if self._is_disabled(stage):
            log.debug("stage_disabled", stage=stage)
            return budget.fallback_value

        t0 = time.monotonic()
        try:
            result = await asyncio.wait_for(
                coro,
                timeout=budget.budget_ms / 1000.0,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._record(stage, latency_ms, exceeded=False)
            return result

        except asyncio.TimeoutError:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._record(stage, latency_ms, exceeded=True)
            self._record_violation(stage)
            log.warning(
                "latency_budget_exceeded",
                stage=stage,
                latency_ms=f"{latency_ms:.1f}",
                budget_ms=budget.budget_ms,
                fallback=budget.fallback_description,
            )
            return budget.fallback_value

        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._record(stage, latency_ms, exceeded=True)
            log.error("stage_error", stage=stage, error=str(exc))
            return budget.fallback_value

    def _record(self, stage: str, latency_ms: float, exceeded: bool) -> None:
        """Record a latency measurement."""
        if stage not in self._records:
            self._records[stage] = []

        records = self._records[stage]
        records.append(LatencyRecord(stage=stage, latency_ms=latency_ms, exceeded=exceeded))

        if len(records) > 1000:
            self._records[stage] = records[-500:]

    def _record_violation(self, stage: str) -> None:
        """Track a budget violation for auto-disable logic."""
        now = time.monotonic()
        if stage not in self._violation_counts:
            self._violation_counts[stage] = []

        violations = self._violation_counts[stage]
        violations.append(now)

        cutoff = now - self._VIOLATION_WINDOW_S
        self._violation_counts[stage] = [t for t in violations if t > cutoff]

        if len(self._violation_counts[stage]) >= self._VIOLATION_THRESHOLD:
            self._disabled_until[stage] = now + self._DISABLE_DURATION_S
            log.warning(
                "stage_auto_disabled",
                stage=stage,
                duration_s=self._DISABLE_DURATION_S,
                violations=len(self._violation_counts[stage]),
            )
            self._violation_counts[stage] = []

    def _is_disabled(self, stage: str) -> bool:
        """Check if a stage is currently disabled due to violations."""
        until = self._disabled_until.get(stage, 0)
        if time.monotonic() < until:
            return True
        if stage in self._disabled_until:
            del self._disabled_until[stage]
        return False

    def report(self, stage: str | None = None) -> dict[str, dict[str, float]]:
        """
        Generate P50/P95/P99 latency report.

        Args:
            stage: Optional stage to report on. If None, reports all stages.

        Returns:
            Dict mapping stage names to percentile stats.
        """
        stages = [stage] if stage else list(self._records.keys())
        report: dict[str, dict[str, float]] = {}

        for s in stages:
            records = self._records.get(s, [])
            if not records:
                continue

            latencies = [r.latency_ms for r in records]
            import numpy as np
            report[s] = {
                "p50": float(np.percentile(latencies, 50)),
                "p95": float(np.percentile(latencies, 95)),
                "p99": float(np.percentile(latencies, 99)),
                "max": float(np.max(latencies)),
                "violations": sum(1 for r in records if r.exceeded),
                "total": len(records),
            }

        return report
