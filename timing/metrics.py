"""
Voice engine performance metrics for Emily.

Exports Prometheus histograms and counters for:
- Per-stage latency (P50/P95/P99)
- Turn detection accuracy
- Backchannel and filler counts
- Interrupt counts and types
- Speculative cache hit rate
"""

from __future__ import annotations

from observability.logger import get_logger

log = get_logger(__name__)

try:
    from prometheus_client import Counter, Histogram, Gauge

    VOICE_STAGE_LATENCY = Histogram(
        "emily_voice_stage_latency_seconds",
        "Latency of each voice pipeline stage",
        ["stage"],
        buckets=[0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0],
    )

    VOICE_TURN_DETECTIONS = Counter(
        "emily_voice_turn_detections_total",
        "Turn detection decisions",
        ["action"],
    )

    VOICE_BACKCHANNELS = Counter(
        "emily_voice_backchannels_total",
        "Backchannels generated",
        ["type"],
    )

    VOICE_INTERRUPTS = Counter(
        "emily_voice_interrupts_total",
        "Interrupts handled",
        ["type"],
    )

    VOICE_FILLERS = Counter(
        "emily_voice_fillers_total",
        "Fillers played",
        ["category"],
    )

    VOICE_SPECULATIVE_CACHE = Counter(
        "emily_voice_speculative_cache_total",
        "Speculative cache outcomes",
        ["outcome"],
    )

    VOICE_PERCEIVED_LATENCY = Histogram(
        "emily_voice_perceived_latency_seconds",
        "End-to-end perceived response latency",
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.5, 2.0],
    )

    VOICE_FSM_STATE = Gauge(
        "emily_voice_fsm_state",
        "Current conversation FSM state (encoded as int)",
    )

    VOICE_EMOTION = Gauge(
        "emily_voice_user_emotion",
        "Detected user emotion dimensions",
        ["dimension"],
    )

except ImportError:

    class _NoOp:
        """No-op metrics when prometheus_client is unavailable."""

        def labels(self, *args: object, **kwargs: object) -> "_NoOp":
            return self

        def observe(self, *args: object) -> None:
            pass

        def inc(self, *args: object) -> None:
            pass

        def set(self, *args: object) -> None:
            pass

    VOICE_STAGE_LATENCY = _NoOp()  # type: ignore[assignment]
    VOICE_TURN_DETECTIONS = _NoOp()  # type: ignore[assignment]
    VOICE_BACKCHANNELS = _NoOp()  # type: ignore[assignment]
    VOICE_INTERRUPTS = _NoOp()  # type: ignore[assignment]
    VOICE_FILLERS = _NoOp()  # type: ignore[assignment]
    VOICE_SPECULATIVE_CACHE = _NoOp()  # type: ignore[assignment]
    VOICE_PERCEIVED_LATENCY = _NoOp()  # type: ignore[assignment]
    VOICE_FSM_STATE = _NoOp()  # type: ignore[assignment]
    VOICE_EMOTION = _NoOp()  # type: ignore[assignment]


def record_stage_latency(stage: str, latency_s: float) -> None:
    """Record a stage latency measurement."""
    VOICE_STAGE_LATENCY.labels(stage=stage).observe(latency_s)


def record_turn_detection(action: str) -> None:
    """Record a turn detection decision."""
    VOICE_TURN_DETECTIONS.labels(action=action).inc()


def record_backchannel(bc_type: str) -> None:
    """Record a backchannel generation."""
    VOICE_BACKCHANNELS.labels(type=bc_type).inc()


def record_interrupt(int_type: str) -> None:
    """Record an interrupt handling."""
    VOICE_INTERRUPTS.labels(type=int_type).inc()


def record_perceived_latency(latency_s: float) -> None:
    """Record end-to-end perceived response latency."""
    VOICE_PERCEIVED_LATENCY.observe(latency_s)
