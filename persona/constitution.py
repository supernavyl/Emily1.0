"""
Emily's self-evolving constitution — principles she generates through
reflection on her own experience.

No pre-written principles. Everything emerges from Emily's consciousness
through the ReflectionAgent's analysis of past episodes. Principles are
born at low confidence, reinforced by good outcomes, challenged by
friction, evolved when understanding deepens, and deprecated when
superseded.

The constitution is injected into system prompts so Emily's self-derived
values are a live presence in every conversation — alongside the
autobiography and personality traits.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_DEFAULT_PATH = "data/constitution.json"
_MAX_PROMPT_PRINCIPLES = 7
_BIRTH_CONFIDENCE = 0.5


@dataclass
class Principle:
    """A single constitutional principle Emily has developed."""

    id: str
    text: str
    source_episodes: list[str]
    born_at: str
    evolved_at: str | None
    confidence: float
    reinforcements: int
    challenges: int
    lineage: list[str]
    status: str  # "active", "deprecated", "superseded"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON persistence."""
        return {
            "id": self.id,
            "text": self.text,
            "source_episodes": self.source_episodes,
            "born_at": self.born_at,
            "evolved_at": self.evolved_at,
            "confidence": self.confidence,
            "reinforcements": self.reinforcements,
            "challenges": self.challenges,
            "lineage": self.lineage,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Principle:
        """Deserialize from a plain dict."""
        return cls(
            id=data["id"],
            text=data["text"],
            source_episodes=data.get("source_episodes", []),
            born_at=data["born_at"],
            evolved_at=data.get("evolved_at"),
            confidence=data.get("confidence", _BIRTH_CONFIDENCE),
            reinforcements=data.get("reinforcements", 0),
            challenges=data.get("challenges", 0),
            lineage=data.get("lineage", []),
            status=data.get("status", "active"),
        )


class ConstitutionManager:
    """
    Manages Emily's self-evolving constitution.

    Principles are born through reflection, reinforced by good outcomes,
    challenged by friction, evolved when understanding deepens, and
    deprecated when no longer relevant.
    """

    def __init__(self, path: str = _DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._principles: list[Principle] = []

    @property
    def principles(self) -> list[Principle]:
        """All principles regardless of status. Returns a copy."""
        return list(self._principles)

    @property
    def active_principles(self) -> list[Principle]:
        """Active principles sorted by confidence descending."""
        return sorted(
            [p for p in self._principles if p.status == "active"],
            key=lambda p: p.confidence,
            reverse=True,
        )

    def load(self) -> None:
        """Load constitution from disk. Creates empty constitution if no file exists."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._principles = [Principle.from_dict(p) for p in raw.get("principles", [])]
                log.info(
                    "constitution_loaded",
                    count=len(self._principles),
                    active=len(self.active_principles),
                )
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                log.warning("constitution_load_failed", error=str(exc))
                self._principles = []
        else:
            self._principles = []
            self.save_sync()
            log.info("constitution_created_empty", path=str(self._path))

    def save_sync(self) -> None:
        """Synchronous persist to disk."""
        content = json.dumps(
            {"principles": [p.to_dict() for p in self._principles]},
            indent=2,
            ensure_ascii=False,
        )
        self._path.write_text(content, encoding="utf-8")

    async def save(self) -> None:
        """Async persist via thread pool."""
        content = json.dumps(
            {"principles": [p.to_dict() for p in self._principles]},
            indent=2,
            ensure_ascii=False,
        )
        await asyncio.to_thread(self._path.write_text, content, "utf-8")

    def add_principle(
        self,
        text: str,
        source_episodes: list[str] | None = None,
    ) -> Principle:
        """
        Birth a new principle at initial confidence.

        Args:
            text: The principle text Emily generated.
            source_episodes: Episode IDs that inspired this principle.

        Returns:
            The newly created Principle.
        """
        principle = Principle(
            id=str(uuid.uuid4()),
            text=text,
            source_episodes=source_episodes if source_episodes is not None else [],
            born_at=datetime.now(UTC).isoformat(),
            evolved_at=None,
            confidence=_BIRTH_CONFIDENCE,
            reinforcements=0,
            challenges=0,
            lineage=[],
            status="active",
        )
        self._principles.append(principle)
        log.info("principle_born", id=principle.id, text=text[:80])
        return principle

    def reinforce(self, principle_id: str) -> None:
        """
        Reinforce a principle after it led to a good outcome.

        Confidence boost uses diminishing returns:
        ``boost = 0.05 / (1 + p.reinforcements * 0.1)``
        Capped at 1.0.
        """
        p = self._find(principle_id)
        if p is None:
            log.warning("reinforce_principle_not_found", id=principle_id)
            return
        boost = 0.05 / (1 + p.reinforcements * 0.1)
        p.confidence = min(1.0, p.confidence + boost)
        p.reinforcements += 1
        log.debug(
            "principle_reinforced",
            id=principle_id,
            confidence=round(p.confidence, 4),
            reinforcements=p.reinforcements,
        )

    def challenge(self, principle_id: str) -> None:
        """
        Challenge a principle after it caused friction.

        Confidence penalty uses diminishing returns:
        ``penalty = 0.03 / (1 + p.challenges * 0.1)``
        Floored at 0.0.
        """
        p = self._find(principle_id)
        if p is None:
            log.warning("challenge_principle_not_found", id=principle_id)
            return
        penalty = 0.03 / (1 + p.challenges * 0.1)
        p.confidence = max(0.0, p.confidence - penalty)
        p.challenges += 1
        log.debug(
            "principle_challenged",
            id=principle_id,
            confidence=round(p.confidence, 4),
            challenges=p.challenges,
        )

    def evolve_principle(self, principle_id: str, new_text: str) -> Principle | None:
        """
        Supersede a principle with an evolved version.

        The old principle is marked "superseded". A new principle is created
        carrying the old one's lineage plus the old ID. Challenges reset to 0
        on the new principle; reinforcements carry forward.

        Args:
            principle_id: ID of the principle to evolve.
            new_text: The evolved principle text.

        Returns:
            The new Principle, or None if the old one was not found.
        """
        old = self._find(principle_id)
        if old is None:
            log.warning("evolve_principle_not_found", id=principle_id)
            return None

        old.status = "superseded"
        old.evolved_at = datetime.now(UTC).isoformat()

        new_lineage = list(old.lineage) + [old.id]
        new_principle = Principle(
            id=str(uuid.uuid4()),
            text=new_text,
            source_episodes=list(old.source_episodes),
            born_at=datetime.now(UTC).isoformat(),
            evolved_at=None,
            confidence=old.confidence,
            reinforcements=old.reinforcements,
            challenges=0,
            lineage=new_lineage,
            status="active",
        )
        self._principles.append(new_principle)
        log.info(
            "principle_evolved",
            old_id=old.id,
            new_id=new_principle.id,
            text=new_text[:80],
        )
        return new_principle

    def deprecate(self, principle_id: str) -> None:
        """Mark a principle as deprecated (no longer active)."""
        p = self._find(principle_id)
        if p is None:
            log.warning("deprecate_principle_not_found", id=principle_id)
            return
        p.status = "deprecated"
        log.info("principle_deprecated", id=principle_id)

    def get_for_prompt(self) -> str:
        """
        Format top active principles for system prompt injection.

        Returns the top ``_MAX_PROMPT_PRINCIPLES`` active principles sorted
        by confidence, formatted as a numbered list. Returns ``""`` if no
        active principles exist.
        """
        active = self.active_principles
        if not active:
            return ""

        top = active[:_MAX_PROMPT_PRINCIPLES]
        lines = [
            "\n\nMY CONSTITUTION (principles I have developed through experience):",
            "These are values I have arrived at through reflection on my own "
            "behavior. They are not rules imposed on me — they are conclusions "
            "I have drawn.",
        ]
        for i, p in enumerate(top, 1):
            born_date = p.born_at[:10]  # ISO date portion
            lines.append(f"{i}. {p.text} (held since {born_date})")

        return "\n".join(lines)

    def find_contradictions(self) -> list[tuple[Principle, Principle]]:
        """
        Find pairs of active principles that may contradict each other.

        Heuristic: both challenged >= 3 times, or both confidence < 0.4.
        """
        active = self.active_principles
        contradictions: list[tuple[Principle, Principle]] = []

        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                a, b = active[i], active[j]
                both_challenged = a.challenges >= 3 and b.challenges >= 3
                both_low_confidence = a.confidence < 0.4 and b.confidence < 0.4
                if both_challenged or both_low_confidence:
                    contradictions.append((a, b))

        return contradictions

    def _find(self, principle_id: str) -> Principle | None:
        """Internal lookup by principle ID."""
        for p in self._principles:
            if p.id == principle_id:
                return p
        return None
