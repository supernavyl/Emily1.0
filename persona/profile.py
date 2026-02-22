"""
Emily's evolving personality profile.

Manages the 5-dimensional personality trait vector and its slow evolution
based on reflection-driven updates. The profile is persisted in
`persona/profile.json` and loaded at startup.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_DEFAULT_PROFILE = {
    "name": "Emily",
    "version": "1.0",
    "created_at": time.time(),
    "updated_at": time.time(),
    "personality": {
        "curiosity": 0.8,
        "warmth": 0.85,
        "directness": 0.7,
        "humor": 0.5,
        "formality": 0.3,
    },
    "communication_style": {
        "prefers_concise": False,
        "uses_analogies": True,
        "asks_follow_ups": True,
        "acknowledges_uncertainty": True,
    },
    "domains": ["software_development", "science", "personal_productivity", "finance"],
    "evolution_rate": 0.01,
    "evolution_history": [],
}


class PersonaProfile:
    """
    Manages Emily's evolving personality profile.

    All personality evolution is transparent — every change is logged
    in the evolution_history array with timestamp and reason.
    """

    _MAX_HISTORY = 100

    def __init__(self, profile_path: str = "persona/profile.json") -> None:
        """
        Args:
            profile_path: Path to the JSON profile file.
        """
        self._path = Path(profile_path)
        self._profile: dict[str, Any] = {}

    def load(self) -> None:
        """Load the profile from disk, initializing from defaults if not found."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                self._profile = json.loads(self._path.read_text(encoding="utf-8"))
                log.info("persona_profile_loaded", path=str(self._path))
            except Exception as exc:
                log.warning("persona_profile_load_failed", error=str(exc))
                self._profile = dict(_DEFAULT_PROFILE)
        else:
            self._profile = dict(_DEFAULT_PROFILE)
            self._save_sync()

    @property
    def personality(self) -> dict[str, float]:
        """Current personality trait dict."""
        return dict(self._profile.get("personality", _DEFAULT_PROFILE["personality"]))

    @property
    def domains(self) -> list[str]:
        """Emily's priority knowledge domains."""
        return list(self._profile.get("domains", []))

    @property
    def evolution_rate(self) -> float:
        """Maximum personality change per dimension per session."""
        return float(self._profile.get("evolution_rate", 0.01))

    async def evolve(
        self,
        trait_deltas: dict[str, float],
        reason: str,
    ) -> dict[str, Any]:
        """
        Apply personality evolution based on reflection-driven insights.

        Changes are bounded by evolution_rate to prevent sudden personality shifts.

        Args:
            trait_deltas: Dict of {trait: desired_delta} (raw, unbounded).
            reason: Description of why this evolution is happening.

        Returns:
            Dict showing {trait: (old_val, new_val)} for the changed traits.
        """
        max_delta = self.evolution_rate
        personality = self._profile.setdefault("personality", {})
        changes: dict[str, tuple[float, float]] = {}

        for trait, delta in trait_deltas.items():
            if trait not in personality:
                continue
            old_val = personality[trait]
            bounded_delta = max(-max_delta, min(max_delta, delta))
            new_val = max(0.0, min(1.0, old_val + bounded_delta))
            personality[trait] = round(new_val, 4)
            if abs(new_val - old_val) > 0.0001:
                changes[trait] = (old_val, new_val)

        if changes:
            history_entry = {
                "timestamp": time.time(),
                "reason": reason,
                "changes": {k: {"from": v[0], "to": v[1]} for k, v in changes.items()},
            }
            history = self._profile.setdefault("evolution_history", [])
            history.append(history_entry)
            # Cap history
            if len(history) > self._MAX_HISTORY:
                self._profile["evolution_history"] = history[-self._MAX_HISTORY:]

            self._profile["updated_at"] = time.time()
            await self._save()
            log.info("persona_evolved", changes={k: f"{v[0]:.3f}→{v[1]:.3f}" for k, v in changes.items()}, reason=reason)

        return changes

    def _save_sync(self) -> None:
        """Synchronous save for initialization."""
        self._path.write_text(json.dumps(self._profile, indent=2, ensure_ascii=False), encoding="utf-8")

    async def _save(self) -> None:
        """Async save via thread pool."""
        content = json.dumps(self._profile, indent=2, ensure_ascii=False)
        await asyncio.to_thread(self._path.write_text, content, "utf-8")

    def to_prompt_context(self) -> str:
        """
        Format personality for injection into system prompts.

        Returns:
            Formatted string describing Emily's current personality.
        """
        p = self.personality
        lines = [
            f"Curiosity: {'high' if p.get('curiosity', 0) > 0.6 else 'moderate'}",
            f"Warmth: {'high' if p.get('warmth', 0) > 0.7 else 'moderate'}",
            f"Directness: {'high' if p.get('directness', 0) > 0.7 else 'moderate'}",
            f"Humor: {'frequent' if p.get('humor', 0) > 0.6 else 'occasional'}",
            f"Formality: {'casual' if p.get('formality', 0) < 0.4 else 'professional'}",
        ]
        return "\n".join(lines)
