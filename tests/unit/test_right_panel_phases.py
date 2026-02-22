"""Tests for the right panel reasoning phase detection and session stats.

Tests the non-Qt logic in :mod:`emily_chat.ui.right_panel` — phase
detection regex, session stats computation, cost breakdown, and
the :class:`ReasoningPhase` data model.
"""

from __future__ import annotations

import pytest

from emily_chat.ui.right_panel import (
    ReasoningPhase,
    compute_session_stats,
    detect_phase,
)


# ------------------------------------------------------------------
# Phase detection
# ------------------------------------------------------------------


class TestDetectPhase:
    """detect_phase regex-based reasoning phase detection."""

    def test_analyzing_keywords(self) -> None:
        """ANALYZING phase should be detected for analysis keywords."""
        assert detect_phase("Let me break down this problem") == ReasoningPhase.ANALYZING
        assert detect_phase("I need to analyze the requirements") == ReasoningPhase.ANALYZING
        assert detect_phase("Looking at the code structure") == ReasoningPhase.ANALYZING
        assert detect_phase("Let me examine this closely") == ReasoningPhase.ANALYZING

    def test_considering_keywords(self) -> None:
        """CONSIDERING phase should be detected for option keywords."""
        assert detect_phase("Let me consider the options") == ReasoningPhase.CONSIDERING
        assert detect_phase("One approach would be to...") == ReasoningPhase.CONSIDERING
        assert detect_phase("Alternatively, we could use...") == ReasoningPhase.CONSIDERING
        assert detect_phase("Let me think about this") == ReasoningPhase.CONSIDERING

    def test_comparing_keywords(self) -> None:
        """COMPARING phase should be detected for comparison keywords."""
        assert detect_phase("Let me compare these two solutions") == ReasoningPhase.COMPARING
        assert detect_phase("Solution A versus solution B") == ReasoningPhase.COMPARING
        assert detect_phase("The trade-off here is significant") == ReasoningPhase.COMPARING
        assert detect_phase("This is better for performance") == ReasoningPhase.COMPARING

    def test_concluding_keywords(self) -> None:
        """CONCLUDING phase should be detected for conclusion keywords."""
        assert detect_phase("Therefore, we should use this") == ReasoningPhase.CONCLUDING
        assert detect_phase("In conclusion, the answer is clear") == ReasoningPhase.CONCLUDING
        assert detect_phase("The final answer is 42") == ReasoningPhase.CONCLUDING
        assert detect_phase("I'll go with the first method") == ReasoningPhase.CONCLUDING

    def test_uncertain_keywords(self) -> None:
        """UNCERTAIN phase should be detected for uncertainty keywords."""
        assert detect_phase("I'm not sure about this") == ReasoningPhase.UNCERTAIN
        assert detect_phase("This is unclear to me") == ReasoningPhase.UNCERTAIN
        assert detect_phase("It could go either way") == ReasoningPhase.UNCERTAIN

    def test_no_phase_detected(self) -> None:
        """Generic text should return None."""
        assert detect_phase("Hello world") is None
        assert detect_phase("The quick brown fox") is None
        assert detect_phase("x = 42") is None

    def test_empty_text(self) -> None:
        """Empty string should return None."""
        assert detect_phase("") is None

    def test_case_insensitive(self) -> None:
        """Detection should be case-insensitive."""
        assert detect_phase("BREAK DOWN the problem") == ReasoningPhase.ANALYZING
        assert detect_phase("THEREFORE we should") == ReasoningPhase.CONCLUDING


# ------------------------------------------------------------------
# ReasoningPhase data model
# ------------------------------------------------------------------


class TestReasoningPhase:
    """ReasoningPhase constants and labels."""

    def test_all_phases_count(self) -> None:
        """There should be 5 phases."""
        assert len(ReasoningPhase.ALL_PHASES) == 5

    def test_labels_complete(self) -> None:
        """Every phase should have a label."""
        for phase in ReasoningPhase.ALL_PHASES:
            assert phase in ReasoningPhase.LABELS

    def test_label_values(self) -> None:
        """Labels should be uppercase strings."""
        for label in ReasoningPhase.LABELS.values():
            assert label == label.upper()

    def test_phase_init(self) -> None:
        """ReasoningPhase instance should store phase and start_time."""
        rp = ReasoningPhase(ReasoningPhase.ANALYZING, 100.0)
        assert rp.phase == "analyzing"
        assert rp.start_time == 100.0
        assert rp.end_time is None
        assert rp.content == ""

    def test_phase_label(self) -> None:
        """label property should return the human-readable name."""
        rp = ReasoningPhase(ReasoningPhase.CONCLUDING, 0.0)
        assert rp.label == "CONCLUDING"


# ------------------------------------------------------------------
# Session stats computation
# ------------------------------------------------------------------


class TestComputeSessionStats:
    """compute_session_stats aggregation logic."""

    def test_empty_messages(self) -> None:
        """Empty list should return zero stats."""
        stats = compute_session_stats([])
        assert stats["messages"] == 0
        assert stats["total_tokens"] == 0
        assert stats["total_cost"] == 0.0
        assert stats["models_used"] == 0
        assert stats["cost_breakdown"] == []

    def test_single_message(self) -> None:
        """Single message should populate all fields."""
        messages = [
            {
                "model": "gpt-5",
                "tokens_in": 100,
                "tokens_out": 200,
                "tokens_thinking": 50,
                "cost_usd": 0.01,
                "latency_ms": 500,
            }
        ]
        stats = compute_session_stats(messages)
        assert stats["messages"] == 1
        assert stats["total_tokens"] == 350
        assert stats["total_cost"] == pytest.approx(0.01)
        assert stats["avg_latency"] == 500
        assert stats["models_used"] == 1

    def test_multiple_messages(self) -> None:
        """Multiple messages should accumulate correctly."""
        messages = [
            {"model": "gpt-5", "tokens_in": 100, "tokens_out": 200, "cost_usd": 0.01, "latency_ms": 500},
            {"model": "gpt-5", "tokens_in": 150, "tokens_out": 300, "cost_usd": 0.02, "latency_ms": 600},
            {"model": "claude", "tokens_in": 200, "tokens_out": 400, "cost_usd": 0.03, "latency_ms": 700},
        ]
        stats = compute_session_stats(messages)
        assert stats["messages"] == 3
        assert stats["total_tokens"] == 100 + 200 + 150 + 300 + 200 + 400
        assert stats["total_cost"] == pytest.approx(0.06)
        assert stats["avg_latency"] == pytest.approx(600.0)
        assert stats["models_used"] == 2

    def test_cost_breakdown_sorted(self) -> None:
        """Cost breakdown should be sorted descending by cost."""
        messages = [
            {"model": "cheap", "cost_usd": 0.01},
            {"model": "expensive", "cost_usd": 0.10},
            {"model": "mid", "cost_usd": 0.05},
        ]
        stats = compute_session_stats(messages)
        breakdown = stats["cost_breakdown"]
        assert len(breakdown) == 3
        assert breakdown[0]["model"] == "expensive"
        assert breakdown[1]["model"] == "mid"
        assert breakdown[2]["model"] == "cheap"

    def test_cost_breakdown_percentages(self) -> None:
        """Percentages should sum to 100 (approximately)."""
        messages = [
            {"model": "a", "cost_usd": 0.25},
            {"model": "b", "cost_usd": 0.75},
        ]
        stats = compute_session_stats(messages)
        breakdown = stats["cost_breakdown"]
        total_pct = sum(e["pct"] for e in breakdown)
        assert total_pct == pytest.approx(100.0)
        b_entry = [e for e in breakdown if e["model"] == "b"][0]
        assert b_entry["pct"] == pytest.approx(75.0)

    def test_missing_fields(self) -> None:
        """Messages with missing fields should use zero defaults."""
        messages = [{"model": "test"}, {}]
        stats = compute_session_stats(messages)
        assert stats["messages"] == 2
        assert stats["total_tokens"] == 0
        assert stats["total_cost"] == 0.0

    def test_none_values(self) -> None:
        """None values in fields should be treated as zero."""
        messages = [
            {
                "model": "test",
                "tokens_in": None,
                "tokens_out": None,
                "cost_usd": None,
                "latency_ms": None,
            }
        ]
        stats = compute_session_stats(messages)
        assert stats["total_tokens"] == 0
        assert stats["total_cost"] == 0.0

    def test_cost_breakdown_with_zero_total(self) -> None:
        """Zero total cost should result in 0% for all models."""
        messages = [{"model": "free", "cost_usd": 0.0}]
        stats = compute_session_stats(messages)
        for entry in stats["cost_breakdown"]:
            assert entry["pct"] == 0

    def test_thinking_tokens_included(self) -> None:
        """Thinking tokens should be included in total."""
        messages = [
            {"tokens_in": 10, "tokens_out": 20, "tokens_thinking": 30}
        ]
        stats = compute_session_stats(messages)
        assert stats["total_tokens"] == 60
