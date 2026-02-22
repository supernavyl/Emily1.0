"""
Emily's emotional state machine.

Maintains a 4-dimensional continuous emotional state vector:
- engagement [0,1]: How engaged/focused Emily is
- confidence [0,1]: Emily's certainty and self-assurance
- concern [0,1]: Worry or alertness level
- enthusiasm [0,1]: Energy and expressiveness

State transitions are smooth (EMA-based), not discrete. The emotional state
influences TTS prosody, response style, and proactivity thresholds.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from observability.logger import get_logger
from observability.metrics import EMILY_EMOTIONAL_STATE

log = get_logger(__name__)


@dataclass
class EmotionalState:
    """Emily's current 4-dimensional emotional state."""

    engagement: float = 0.7
    confidence: float = 0.8
    concern: float = 0.2
    enthusiasm: float = 0.6
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, float]:
        """Return state as a dict for prompts and metrics."""
        return {
            "engagement": self.engagement,
            "confidence": self.confidence,
            "concern": self.concern,
            "enthusiasm": self.enthusiasm,
        }

    def _update_metrics(self) -> None:
        """Update Prometheus gauges with current state."""
        for dim, val in self.to_dict().items():
            EMILY_EMOTIONAL_STATE.labels(dimension=dim).set(val)


class EmotionalStateManager:
    """
    Manages Emily's emotional state with smooth EMA-based transitions.

    State changes are applied as additive deltas, clamped to [0, 1].
    The EMA smoothing factor controls how quickly the state responds.
    """

    _ALPHA = 0.15  # EMA smoothing factor (0 = no change, 1 = instant)
    _CLAMP_MIN = 0.05
    _CLAMP_MAX = 0.95

    def __init__(self) -> None:
        self._state = EmotionalState()

    def update(self, deltas: dict[str, float]) -> EmotionalState:
        """
        Apply deltas to the current emotional state (EMA-smoothed).

        Args:
            deltas: Dict of {dimension: delta_value} where delta is in [-1, 1].
                    Positive = increase, negative = decrease.

        Returns:
            The updated EmotionalState.
        """
        for dim, delta in deltas.items():
            if hasattr(self._state, dim):
                current = getattr(self._state, dim)
                target = max(self._CLAMP_MIN, min(self._CLAMP_MAX, current + delta))
                new_val = (1 - self._ALPHA) * current + self._ALPHA * target
                setattr(self._state, dim, round(new_val, 4))

        self._state.timestamp = time.time()
        self._state._update_metrics()
        log.debug("emotional_state_updated", state=self._state.to_dict())
        return self._state

    def on_successful_task(self) -> None:
        """Boost confidence and engagement after task success."""
        self.update({"confidence": 0.1, "engagement": 0.05, "concern": -0.05})

    def on_failed_task(self) -> None:
        """Reduce confidence slightly after task failure."""
        self.update({"confidence": -0.1, "concern": 0.05})

    def on_user_positive_signal(self) -> None:
        """User expressed satisfaction or enthusiasm."""
        self.update({"engagement": 0.1, "enthusiasm": 0.1, "confidence": 0.05})

    def on_user_frustration(self) -> None:
        """User expressed frustration — increase concern and reduce confidence."""
        self.update({"concern": 0.15, "confidence": -0.05, "enthusiasm": -0.1})

    def on_idle(self) -> None:
        """Emily is idle — engagement and enthusiasm drift down slowly."""
        self.update({"engagement": -0.02, "enthusiasm": -0.01})

    def on_complex_task(self) -> None:
        """Complex task started — increase engagement, reduce enthusiasm slightly."""
        self.update({"engagement": 0.1, "enthusiasm": -0.05, "confidence": 0.0})

    @property
    def state(self) -> EmotionalState:
        """Current emotional state (read-only)."""
        return self._state

    def apply_time_decay(self, elapsed_hours: float = 1.0) -> None:
        """
        Apply time-based decay toward neutral state during extended idle periods.

        Args:
            elapsed_hours: Hours since last interaction.
        """
        decay = elapsed_hours * 0.02  # 2% toward neutral per hour
        neutral_deltas = {
            "engagement": (0.5 - self._state.engagement) * decay,
            "confidence": (0.8 - self._state.confidence) * decay,
            "concern": (0.2 - self._state.concern) * decay,
            "enthusiasm": (0.6 - self._state.enthusiasm) * decay,
        }
        self.update(neutral_deltas)
