"""
Tier 5: Procedural + Identity Memory — structured facts and skill library.

Stores:
- User profile: extracted facts about the user (name, preferences, goals)
- Emily's self-model: capabilities, limitations, learned strategies
- World model: Emily's current beliefs about ongoing projects and context
- Skill library: successful tool call sequences for reuse

Backed by a JSON file for easy inspection and manual editing.
Extended to Qdrant for fuzzy retrieval in Phase 11.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from config import ProceduralMemoryConfig
from observability.logger import get_logger
from observability.metrics import MEMORY_READS_TOTAL, MEMORY_WRITES_TOTAL

log = get_logger(__name__)

_DEFAULT_STRUCTURE: dict[str, Any] = {
    "user_profile": {
        "name": None,
        "preferences": {},
        "relationships": {},
        "recurring_topics": [],
        "goals": [],
        "facts": {},
    },
    "emily_self_model": {
        "capabilities": [],
        "known_limitations": [],
        "successful_strategies": [],
        "personality_trajectory": [],
        "prompt_version": "v1.0",
        "last_reflection": None,
    },
    "world_model": {
        "active_projects": {},
        "ongoing_tasks": [],
        "current_context": {},
    },
    "skill_library": [],
}


class ProceduralMemory:
    """
    JSON-backed procedural and identity memory.

    Provides typed accessors for each sub-section and debounced disk writes
    (writes are batched and flushed at most every N seconds to avoid thrashing).
    """

    _WRITE_DEBOUNCE_S = 5.0

    def __init__(self, config: ProceduralMemoryConfig) -> None:
        """
        Args:
            config: Procedural memory configuration.
        """
        self._path = Path(config.path)
        self._data: dict[str, Any] = {}
        self._dirty = False
        self._last_flush = 0.0

    async def load(self) -> None:
        """Load the procedural memory from disk, initializing if not found."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                raw = await asyncio.to_thread(self._path.read_text, "utf-8")
                self._data = json.loads(raw)
                # Merge any missing keys from default structure
                for key, value in _DEFAULT_STRUCTURE.items():
                    if key not in self._data:
                        self._data[key] = value
                log.info("procedural_memory_loaded", path=str(self._path))
            except Exception as exc:
                log.warning("procedural_memory_load_failed", error=str(exc), using_defaults=True)
                self._data = dict(_DEFAULT_STRUCTURE)
        else:
            self._data = dict(_DEFAULT_STRUCTURE)
            await self._flush()

    async def _flush(self) -> None:
        """Write current state to disk."""
        await asyncio.to_thread(
            self._path.write_text,
            json.dumps(self._data, indent=2, ensure_ascii=False),
            "utf-8",
        )
        self._dirty = False
        self._last_flush = time.monotonic()
        MEMORY_WRITES_TOTAL.labels(tier="procedural").inc()

    async def _maybe_flush(self) -> None:
        """Flush to disk if dirty and debounce period has passed."""
        if self._dirty and (time.monotonic() - self._last_flush) >= self._WRITE_DEBOUNCE_S:
            await self._flush()

    # --- User profile ---

    def get_user_fact(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a user fact by key.

        Args:
            key: Fact key (e.g., "name", "preferred_language").
            default: Default value if not found.

        Returns:
            The fact value or default.
        """
        MEMORY_READS_TOTAL.labels(tier="procedural").inc()
        return self._data["user_profile"]["facts"].get(key, default)

    async def set_user_fact(self, key: str, value: Any) -> None:
        """
        Store a user fact.

        Args:
            key: Fact key.
            value: Fact value (must be JSON-serializable).
        """
        self._data["user_profile"]["facts"][key] = value
        self._dirty = True
        await self._maybe_flush()
        log.debug("user_fact_set", key=key, value=str(value)[:50])

    async def update_user_profile(self, updates: dict[str, Any]) -> None:
        """
        Merge updates into the user profile.

        Args:
            updates: Dict of fields to update in the user_profile section.
        """
        self._data["user_profile"].update(updates)
        self._dirty = True
        await self._maybe_flush()

    @property
    def user_profile(self) -> dict[str, Any]:
        """Read-only view of the user profile."""
        MEMORY_READS_TOTAL.labels(tier="procedural").inc()
        return dict(self._data["user_profile"])

    @property
    def is_new_user(self) -> bool:
        """True if no user name has been set yet (first-run / onboarding needed)."""
        return self._data.get("user_profile", {}).get("name") is None

    # --- Emily self-model ---

    async def update_self_model(self, updates: dict[str, Any]) -> None:
        """
        Update Emily's self-model.

        Args:
            updates: Dict of fields to update.
        """
        self._data["emily_self_model"].update(updates)
        self._data["emily_self_model"]["last_reflection"] = time.time()
        self._dirty = True
        await self._maybe_flush()

    async def add_successful_strategy(self, strategy: str) -> None:
        """
        Log a successful problem-solving strategy for future reuse.

        Args:
            strategy: Text description of the strategy.
        """
        strategies = self._data["emily_self_model"]["successful_strategies"]
        if strategy not in strategies:
            strategies.append(strategy)
            if len(strategies) > 100:  # Cap list size
                strategies.pop(0)
        self._dirty = True
        await self._maybe_flush()

    @property
    def self_model(self) -> dict[str, Any]:
        """Read-only view of Emily's self-model."""
        return dict(self._data["emily_self_model"])

    # --- Skill library ---

    async def add_skill(
        self,
        name: str,
        description: str,
        tool_sequence: list[dict[str, Any]],
        success_count: int = 1,
    ) -> None:
        """
        Add a successful tool sequence to the skill library.

        Args:
            name: Short skill name.
            description: What this skill does.
            tool_sequence: Ordered list of tool call dicts.
            success_count: How many times this sequence has succeeded.
        """
        skill = {
            "name": name,
            "description": description,
            "tool_sequence": tool_sequence,
            "success_count": success_count,
            "created_at": time.time(),
        }
        library = self._data["skill_library"]
        # Update if exists, append if new
        for existing in library:
            if existing["name"] == name:
                existing["success_count"] += 1
                existing["tool_sequence"] = tool_sequence
                break
        else:
            library.append(skill)

        self._dirty = True
        await self._maybe_flush()

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        """
        Simple keyword search of the skill library.

        Args:
            query: Search terms.

        Returns:
            Matching skill records.
        """
        query_lower = query.lower()
        return [
            s for s in self._data["skill_library"]
            if query_lower in s["name"].lower() or query_lower in s["description"].lower()
        ]

    async def close(self) -> None:
        """Flush any pending writes and close."""
        if self._dirty:
            await self._flush()
