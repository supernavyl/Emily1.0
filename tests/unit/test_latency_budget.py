"""Unit tests for timing.latency_budget.LatencyBudget."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

from timing.latency_budget import LatencyBudget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def fast_coro(value: str = "ok") -> str:
    """Completes instantly."""
    return value


async def slow_coro(delay: float = 1.0) -> str:
    """Takes longer than most budgets."""
    await asyncio.sleep(delay)
    return "slow_result"


async def failing_coro() -> str:
    """Raises an exception."""
    raise ValueError("stage broke")


# ---------------------------------------------------------------------------
# Basic budget enforcement
# ---------------------------------------------------------------------------


class TestLatencyBudget:
    def test_fast_coro_returns_result(self):
        lb = LatencyBudget()
        result = asyncio.get_event_loop().run_until_complete(
            lb.check_stage("vad", fast_coro("vad_ok"))
        )
        assert result == "vad_ok"

    def test_slow_coro_returns_fallback(self):
        lb = LatencyBudget()
        # VAD budget is 5ms, slow_coro sleeps 1s → timeout
        result = asyncio.get_event_loop().run_until_complete(lb.check_stage("vad", slow_coro(1.0)))
        assert result == 0.5  # Default VAD fallback

    def test_unknown_stage_passes_through(self):
        lb = LatencyBudget()
        result = asyncio.get_event_loop().run_until_complete(
            lb.check_stage("nonexistent", fast_coro("pass"))
        )
        assert result == "pass"

    def test_exception_returns_fallback(self):
        lb = LatencyBudget()
        result = asyncio.get_event_loop().run_until_complete(lb.check_stage("vad", failing_coro()))
        assert result == 0.5  # VAD fallback

    def test_set_budget_overrides_default(self):
        lb = LatencyBudget()
        lb.set_budget("custom_stage", budget_ms=10.0, fallback="custom_fallback")

        # Fast coro returns its value
        result = asyncio.get_event_loop().run_until_complete(
            lb.check_stage("custom_stage", fast_coro("real"))
        )
        assert result == "real"


# ---------------------------------------------------------------------------
# Auto-disable after repeated violations
# ---------------------------------------------------------------------------


class TestAutoDisable:
    def test_three_violations_disable_stage(self):
        lb = LatencyBudget()
        # Set a very tight budget so slow_coro always exceeds
        lb.set_budget("test_stage", budget_ms=1.0, fallback="fallback")

        loop = asyncio.get_event_loop()
        for _ in range(3):
            loop.run_until_complete(lb.check_stage("test_stage", slow_coro(0.1)))

        # Stage should now be disabled
        assert lb._is_disabled("test_stage")

    def test_disabled_stage_returns_fallback_immediately(self):
        lb = LatencyBudget()
        lb.set_budget("test_stage", budget_ms=1.0, fallback="fb")

        loop = asyncio.get_event_loop()
        for _ in range(3):
            loop.run_until_complete(lb.check_stage("test_stage", slow_coro(0.1)))

        # This should return immediately without running coro
        result = loop.run_until_complete(
            lb.check_stage("test_stage", fast_coro("should_not_reach"))
        )
        assert result == "fb"

    def test_stage_re_enables_after_timeout(self):
        lb = LatencyBudget()
        lb.set_budget("test_stage", budget_ms=1.0, fallback="fb")

        loop = asyncio.get_event_loop()
        for _ in range(3):
            loop.run_until_complete(lb.check_stage("test_stage", slow_coro(0.1)))

        assert lb._is_disabled("test_stage")

        # Fast-forward past the disable duration
        with patch.object(time, "monotonic", return_value=time.monotonic() + 60):
            assert not lb._is_disabled("test_stage")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_empty_without_records(self):
        lb = LatencyBudget()
        assert lb.report() == {}

    def test_report_returns_percentiles(self):
        lb = LatencyBudget()

        loop = asyncio.get_event_loop()
        # Run a few fast stages to build records
        for _ in range(10):
            loop.run_until_complete(lb.check_stage("vad", fast_coro("ok")))

        report = lb.report("vad")
        assert "vad" in report
        stats = report["vad"]
        assert "p50" in stats
        assert "p95" in stats
        assert "p99" in stats
        assert stats["total"] == 10
        assert stats["violations"] == 0

    def test_report_tracks_violations(self):
        lb = LatencyBudget()
        lb.set_budget("slow_stage", budget_ms=1.0, fallback=None)

        loop = asyncio.get_event_loop()
        loop.run_until_complete(lb.check_stage("slow_stage", slow_coro(0.1)))

        report = lb.report("slow_stage")
        assert report["slow_stage"]["violations"] == 1
        assert report["slow_stage"]["total"] == 1
