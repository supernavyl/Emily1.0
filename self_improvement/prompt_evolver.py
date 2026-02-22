"""
Prompt evolver for Emily's self-improvement engine.

Performs A/B testing of prompt variants and automatically promotes
high-performing variants using a multi-armed bandit (epsilon-greedy) strategy.

Architecture:
- Each prompt slot (e.g., "system_prompt", "rag_prompt", "critic_prompt")
  can have multiple versioned variants stored in `prompts/`.
- The evolver tracks win/loss/score for each variant.
- After a configurable number of samples, the best-performing variant
  is promoted as the new default.
- Retired variants are archived to `prompts/archive/`.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_STATS_PATH = Path("data/prompt_stats.json")
_PROMPTS_DIR = Path("prompts")
_ARCHIVE_DIR = Path("prompts/archive")


@dataclass
class PromptVariant:
    """A single versioned prompt variant."""

    slot: str           # e.g., "system_prompt"
    version: str        # e.g., "v1", "v2"
    content: str
    wins: int = 0
    losses: int = 0
    total_score: float = 0.0
    created_at: float = field(default_factory=time.time)
    promoted_at: float | None = None

    @property
    def sample_count(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        if self.sample_count == 0:
            return 0.5
        return self.wins / self.sample_count

    @property
    def avg_score(self) -> float:
        if self.sample_count == 0:
            return 0.0
        return self.total_score / self.sample_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "version": self.version,
            "wins": self.wins,
            "losses": self.losses,
            "total_score": self.total_score,
            "created_at": self.created_at,
            "promoted_at": self.promoted_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], content: str = "") -> "PromptVariant":
        v = cls(
            slot=data["slot"],
            version=data["version"],
            content=content,
            wins=data.get("wins", 0),
            losses=data.get("losses", 0),
            total_score=data.get("total_score", 0.0),
            created_at=data.get("created_at", time.time()),
            promoted_at=data.get("promoted_at"),
        )
        return v


class PromptEvolver:
    """
    A/B tester and evolver for LLM prompts.

    Uses epsilon-greedy exploration: with probability `epsilon`, selects
    a random variant (explore); otherwise, selects the highest-scoring
    variant (exploit).
    """

    _MIN_SAMPLES_TO_PROMOTE = 20
    _PROMOTION_WIN_RATE_THRESHOLD = 0.60
    _EPSILON = 0.15  # 15% exploration rate

    def __init__(
        self,
        prompts_dir: Path = _PROMPTS_DIR,
        stats_path: Path = _STATS_PATH,
        epsilon: float = _EPSILON,
    ) -> None:
        """
        Args:
            prompts_dir: Directory containing prompt text files.
            stats_path: Path to the JSON file storing variant statistics.
            epsilon: Exploration rate for epsilon-greedy selection.
        """
        self._prompts_dir = prompts_dir
        self._stats_path = stats_path
        self._epsilon = epsilon
        self._variants: dict[str, list[PromptVariant]] = {}  # slot → variants
        self._load_stats()

    def _load_stats(self) -> None:
        """Load variant statistics from disk."""
        if not self._stats_path.exists():
            return
        try:
            data = json.loads(self._stats_path.read_text())
            for slot, variants in data.items():
                loaded = []
                for v_data in variants:
                    content = self._load_prompt_file(slot, v_data["version"])
                    loaded.append(PromptVariant.from_dict(v_data, content))
                self._variants[slot] = loaded
        except Exception as exc:
            log.error("prompt_stats_load_error", error=str(exc))

    def _save_stats(self) -> None:
        """Persist variant statistics to disk."""
        self._stats_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            slot: [v.to_dict() for v in variants]
            for slot, variants in self._variants.items()
        }
        self._stats_path.write_text(json.dumps(data, indent=2))

    def _load_prompt_file(self, slot: str, version: str) -> str:
        """Load prompt content from a file."""
        path = self._prompts_dir / f"{slot}_{version}.txt"
        if path.exists():
            return path.read_text().strip()
        return ""

    def register_variant(self, slot: str, version: str, content: str) -> None:
        """
        Register a new prompt variant for A/B testing.

        Args:
            slot: Prompt slot name (e.g., "system_prompt").
            version: Version identifier (e.g., "v2").
            content: Prompt text content.
        """
        if slot not in self._variants:
            self._variants[slot] = []

        # Check if already registered
        for v in self._variants[slot]:
            if v.version == version:
                v.content = content
                return

        variant = PromptVariant(slot=slot, version=version, content=content)
        self._variants[slot].append(variant)

        # Save to file
        self._prompts_dir.mkdir(parents=True, exist_ok=True)
        (self._prompts_dir / f"{slot}_{version}.txt").write_text(content)

        self._save_stats()
        log.info("prompt_variant_registered", slot=slot, version=version)

    def select_variant(self, slot: str) -> PromptVariant | None:
        """
        Select a prompt variant using epsilon-greedy strategy.

        Args:
            slot: Prompt slot name.

        Returns:
            Selected PromptVariant, or None if no variants registered.
        """
        variants = self._variants.get(slot, [])
        if not variants:
            return None

        if random.random() < self._epsilon:
            # Explore: random variant
            return random.choice(variants)

        # Exploit: highest avg_score (ties broken by win_rate)
        return max(variants, key=lambda v: (v.avg_score, v.win_rate))

    def record_outcome(
        self,
        slot: str,
        version: str,
        score: float,
        won: bool,
    ) -> None:
        """
        Record the outcome of a prompt variant being used.

        Args:
            slot: Prompt slot name.
            version: Variant version that was used.
            score: Quality score (0.0–1.0) from the critic.
            won: True if this response was considered successful.
        """
        variants = self._variants.get(slot, [])
        for v in variants:
            if v.version == version:
                v.total_score += score
                if won:
                    v.wins += 1
                else:
                    v.losses += 1
                log.debug(
                    "prompt_outcome_recorded",
                    slot=slot,
                    version=version,
                    score=score,
                    won=won,
                    win_rate=f"{v.win_rate:.2f}",
                )
                break

        self._save_stats()
        self._maybe_promote(slot)

    def _maybe_promote(self, slot: str) -> None:
        """
        Check if any variant deserves promotion to default.

        Promotes a variant if it has sufficient samples and outperforms
        all others by the configured threshold.
        """
        variants = self._variants.get(slot, [])
        if len(variants) < 2:
            return

        best = max(variants, key=lambda v: v.avg_score)
        if (best.sample_count >= self._MIN_SAMPLES_TO_PROMOTE
                and best.win_rate >= self._PROMOTION_WIN_RATE_THRESHOLD):
            # Archive non-best variants
            for v in variants:
                if v.version != best.version:
                    self._archive_variant(slot, v)

            best.promoted_at = time.time()
            self._variants[slot] = [best]
            self._save_stats()
            log.info(
                "prompt_variant_promoted",
                slot=slot,
                version=best.version,
                win_rate=f"{best.win_rate:.2f}",
                avg_score=f"{best.avg_score:.3f}",
            )

    def _archive_variant(self, slot: str, variant: PromptVariant) -> None:
        """Move a prompt variant file to the archive directory."""
        _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        src = self._prompts_dir / f"{slot}_{variant.version}.txt"
        if src.exists():
            ts = int(time.time())
            dst = _ARCHIVE_DIR / f"{slot}_{variant.version}_{ts}.txt"
            src.rename(dst)
            log.info("prompt_variant_archived", slot=slot, version=variant.version)

    def get_stats(self, slot: str) -> list[dict[str, Any]]:
        """
        Get statistics for all variants of a slot.

        Args:
            slot: Prompt slot name.

        Returns:
            List of dicts with variant statistics.
        """
        return [
            {**v.to_dict(), "win_rate": v.win_rate, "avg_score": v.avg_score}
            for v in self._variants.get(slot, [])
        ]

    def generate_evolved_variant(self, slot: str, current_content: str, feedback: str) -> str:
        """
        Use feedback to suggest an evolved prompt variant.

        This method returns a mutated version of the current prompt
        incorporating the feedback. In production, this would call
        the smart LLM; here we return a tagged placeholder for the
        ReflectionAgent to fill in asynchronously.

        Args:
            slot: Prompt slot name.
            current_content: Current best-performing prompt text.
            feedback: Structured feedback from the CriticAgent.

        Returns:
            Evolved prompt text suggestion.
        """
        # The ReflectionAgent calls this and uses the LLM to generate the actual variant.
        # We store the mutation request for async processing.
        mutation_request = {
            "slot": slot,
            "base_content": current_content,
            "feedback": feedback,
            "requested_at": time.time(),
        }
        mutation_queue = Path("data/prompt_mutation_queue.jsonl")
        with open(mutation_queue, "a") as f:
            f.write(json.dumps(mutation_request) + "\n")
        log.info("prompt_mutation_queued", slot=slot)
        return current_content  # Return current while async mutation runs
