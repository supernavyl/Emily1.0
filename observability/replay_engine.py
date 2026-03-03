"""
Read-only replay engine for Emily's Agent Replay Debugger.

Loads a session JSONL file (plain or gzipped) and provides random-access
inspection: step through events, filter by category/agent/message type,
trace a single agent's activity, or follow a task across agents.

No handlers are re-executed — this is pure log inspection.

Usage:
    engine = ReplayEngine.load("data/replay/abc123.jsonl")
    for ts, summary in engine.timeline():
        print(f"{ts:.3f}  {summary}")

    for event in engine.agent_trace("ConversationAgent"):
        print(event)
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ReplayEvent:
    """Single deserialized event from a session JSONL file."""

    ts: float
    cat: str
    kind: str
    data: dict[str, Any]
    seq: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ReplayEvent:
        return cls(
            ts=raw.get("ts", 0.0),
            cat=raw.get("cat", ""),
            kind=raw.get("kind", ""),
            data=raw.get("data", {}),
            seq=raw.get("seq", 0),
        )

    def summary(self) -> str:
        """One-line human-readable summary."""
        parts = [self.cat, self.kind]
        # Add agent/sender info when available
        sender = self.data.get("sender", "")
        recipient = self.data.get("recipient", "")
        msg_type = self.data.get("type", "")
        if sender:
            parts.append(f"{sender}->{recipient}")
        if msg_type:
            parts.append(msg_type)
        return " | ".join(p for p in parts if p)


class ReplayEngine:
    """Read-only replay over a recorded session.

    Events are loaded eagerly into memory (typical sessions are <10 MB)
    and indexed by sequence number for O(1) random access.
    """

    def __init__(self, events: list[ReplayEvent], source: str = "") -> None:
        # Sort by seq to guarantee order
        self._events = sorted(events, key=lambda e: e.seq)
        self._source = source
        self._cursor = 0
        # Index: seq -> list position
        self._seq_index: dict[int, int] = {e.seq: i for i, e in enumerate(self._events)}

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> ReplayEngine:
        """Load a session from a ``.jsonl`` or ``.jsonl.gz`` file."""
        p = Path(path)
        events: list[ReplayEvent] = []

        opener = gzip.open if p.suffix == ".gz" else open
        with opener(p, "rt", encoding="utf-8") as fh:  # type: ignore[call-overload]
            for _line_no, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                    events.append(ReplayEvent.from_dict(raw))
                except json.JSONDecodeError:
                    continue  # skip corrupt lines

        return cls(events, source=str(p))

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def step(self) -> ReplayEvent | None:
        """Advance cursor by one and return the event (or None at end)."""
        if self._cursor >= len(self._events):
            return None
        event = self._events[self._cursor]
        self._cursor += 1
        return event

    def step_back(self) -> ReplayEvent | None:
        """Move cursor back by one and return the event."""
        if self._cursor <= 0:
            return None
        self._cursor -= 1
        return self._events[self._cursor]

    def step_to(self, seq: int) -> ReplayEvent | None:
        """Jump to the event with the given sequence number."""
        idx = self._seq_index.get(seq)
        if idx is None:
            return None
        self._cursor = idx + 1  # cursor points to *next* event
        return self._events[idx]

    def peek(self) -> ReplayEvent | None:
        """Return the current event without advancing."""
        if self._cursor >= len(self._events):
            return None
        return self._events[self._cursor]

    def reset(self) -> None:
        """Reset cursor to the beginning."""
        self._cursor = 0

    @property
    def position(self) -> int:
        """Current cursor position (0-based)."""
        return self._cursor

    @property
    def total(self) -> int:
        """Total number of events in the session."""
        return len(self._events)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter(
        self,
        *,
        cat: str | None = None,
        agent: str | None = None,
        msg_type: str | None = None,
        kind: str | None = None,
    ) -> list[ReplayEvent]:
        """Return events matching all provided filters."""
        result: list[ReplayEvent] = []
        for e in self._events:
            if cat is not None and e.cat != cat:
                continue
            if kind is not None and e.kind != kind:
                continue
            if agent is not None:
                sender = e.data.get("sender", "")
                recipient = e.data.get("recipient", "")
                if agent != sender and agent != recipient:
                    continue
            if msg_type is not None and e.data.get("type", "") != msg_type:
                continue
            result.append(e)
        return result

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------

    def timeline(self) -> list[tuple[float, str]]:
        """Return ``(timestamp, summary)`` pairs for every event."""
        return [(e.ts, e.summary()) for e in self._events]

    def agent_trace(self, agent_name: str) -> list[ReplayEvent]:
        """All events where *agent_name* is sender or recipient."""
        return self.filter(agent=agent_name)

    def task_trace(self, task_id: str) -> list[ReplayEvent]:
        """Follow a task across agents by matching ``task_id`` in event data."""
        result: list[ReplayEvent] = []
        for e in self._events:
            if e.data.get("task_id") == task_id:
                result.append(e)
        return result

    def categories(self) -> list[str]:
        """Return sorted list of unique categories in this session."""
        return sorted({e.cat for e in self._events})

    def agents(self) -> list[str]:
        """Return sorted list of unique agent names (senders + recipients)."""
        names: set[str] = set()
        for e in self._events:
            s = e.data.get("sender", "")
            r = e.data.get("recipient", "")
            if s:
                names.add(s)
            if r:
                names.add(r)
        return sorted(names)

    def time_range(self) -> tuple[float, float]:
        """Return ``(earliest_ts, latest_ts)``."""
        if not self._events:
            return (0.0, 0.0)
        return (self._events[0].ts, self._events[-1].ts)

    def events_between(self, start_ts: float, end_ts: float) -> list[ReplayEvent]:
        """Return events within a timestamp range (inclusive)."""
        return [e for e in self._events if start_ts <= e.ts <= end_ts]

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[ReplayEvent]:
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def __repr__(self) -> str:
        return f"ReplayEngine(events={len(self._events)}, source={self._source!r})"
