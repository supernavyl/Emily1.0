"""
Tamper-evident audit log for Emily.

Every security-relevant event (tool execution, agent decisions,
file writes, external API calls, consent approvals/denials) is
appended to an append-only JSONL file with a cryptographic chain:
each entry contains the SHA-256 hash of the previous entry, forming
a hash chain. Any tampering invalidates the chain.

Log format per line (JSONL):
{
  "seq": 42,
  "ts": "2025-01-01T00:00:00.000Z",
  "event": "tool_executed",
  "actor": "ReActLoop",
  "payload": {...},
  "prev_hash": "abc123...",
  "entry_hash": "def456..."
}
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_NULL_HASH = "0" * 64  # Genesis block hash


@dataclass
class AuditEntry:
    """A single audit log entry."""

    event: str
    actor: str
    payload: dict[str, Any]
    seq: int = 0
    ts: float = field(default_factory=time.time)
    prev_hash: str = _NULL_HASH
    entry_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "event": self.event,
            "actor": self.actor,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEntry":
        entry = cls(
            event=data["event"],
            actor=data["actor"],
            payload=data.get("payload", {}),
            seq=data.get("seq", 0),
            ts=data.get("ts", 0.0),
            prev_hash=data.get("prev_hash", _NULL_HASH),
            entry_hash=data.get("entry_hash", ""),
        )
        return entry


def _hash_entry(entry_dict: dict[str, Any]) -> str:
    """Compute SHA-256 hash of the serialized entry (without entry_hash field)."""
    data = {k: v for k, v in entry_dict.items() if k != "entry_hash"}
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


class AuditLog:
    """
    Append-only, hash-chained audit log.

    Thread-safe via asyncio lock. All appends are serialized.
    Can verify the integrity of the full log at any time.
    """

    def __init__(self, path: str = "logs/audit.log") -> None:
        """
        Args:
            path: Path to the JSONL audit log file.
        """
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._seq = 0
        self._last_hash = _NULL_HASH
        self._initialized = False

    async def _ensure_initialized(self) -> None:
        """Load the last sequence number and hash from existing log."""
        if self._initialized:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if self._path.exists():
            try:
                lines = self._path.read_text().strip().splitlines()
                if lines:
                    last = json.loads(lines[-1])
                    self._seq = last.get("seq", 0) + 1
                    self._last_hash = last.get("entry_hash", _NULL_HASH)
            except Exception as exc:
                log.warning("audit_log_load_error", error=str(exc))
        self._initialized = True

    async def append(
        self,
        event: str,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> AuditEntry:
        """
        Append a new event to the audit log.

        Args:
            event: Event type identifier (e.g., "tool_executed", "consent_approved").
            actor: The agent/module that generated this event.
            payload: Structured payload for the event.

        Returns:
            The committed AuditEntry.
        """
        async with self._lock:
            await self._ensure_initialized()

            entry = AuditEntry(
                event=event,
                actor=actor,
                payload=payload or {},
                seq=self._seq,
                ts=time.time(),
                prev_hash=self._last_hash,
            )

            entry_dict = entry.to_dict()
            entry.entry_hash = _hash_entry(entry_dict)
            entry_dict["entry_hash"] = entry.entry_hash

            # Append to file (O_APPEND for atomic writes on Linux)
            line = json.dumps(entry_dict, ensure_ascii=True) + "\n"
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)

            self._seq += 1
            self._last_hash = entry.entry_hash

            log.debug(
                "audit_event",
                audit_event=event,
                actor=actor,
                seq=entry.seq,
            )
            return entry

    async def verify(self) -> tuple[bool, list[str]]:
        """
        Verify the integrity of the entire audit log.

        Returns:
            Tuple of (is_valid, list_of_errors). is_valid is True iff no errors found.
        """
        errors: list[str] = []
        if not self._path.exists():
            return True, []

        lines = self._path.read_text().strip().splitlines()
        if not lines:
            return True, []

        prev_hash = _NULL_HASH
        for i, line in enumerate(lines):
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"Line {i}: JSON parse error: {exc}")
                continue

            stored_hash = data.get("entry_hash", "")
            computed_hash = _hash_entry(data)

            if stored_hash != computed_hash:
                errors.append(f"Line {i} (seq {data.get('seq')}): hash mismatch (tampered?)")
                continue

            if data.get("prev_hash") != prev_hash:
                errors.append(
                    f"Line {i} (seq {data.get('seq')}): chain broken — "
                    f"expected prev_hash={prev_hash!r}, got {data.get('prev_hash')!r}"
                )

            prev_hash = stored_hash

        if errors:
            log.error("audit_log_integrity_failure", error_count=len(errors))
        else:
            log.info("audit_log_verified_ok", entries=len(lines))

        return len(errors) == 0, errors

    async def get_recent(self, n: int = 50) -> list[AuditEntry]:
        """
        Retrieve the most recent N audit entries.

        Args:
            n: Number of entries to return.

        Returns:
            List of AuditEntry objects, most recent last.
        """
        if not self._path.exists():
            return []
        lines = self._path.read_text().strip().splitlines()
        recent = lines[-n:]
        entries = []
        for line in recent:
            try:
                entries.append(AuditEntry.from_dict(json.loads(line)))
            except Exception:
                pass
        return entries

    async def trim_retention_days(self, days: int) -> int:
        """
        Keep only entries from the last N days; rewrite log with recomputed chain.

        Args:
            days: Retain entries with ts >= (now - days * 86400).

        Returns:
            Number of entries removed.
        """
        if days <= 0 or not self._path.exists():
            return 0
        async with self._lock:
            await self._ensure_initialized()
        cutoff = time.time() - (days * 86400.0)
        lines = self._path.read_text().strip().splitlines()
        kept: list[dict[str, Any]] = []
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("ts", 0) >= cutoff:
                    kept.append(data)
            except json.JSONDecodeError:
                pass
        removed = len(lines) - len(kept)
        if removed == 0:
            return 0
        # Rewrite with recomputed hash chain
        prev_hash = _NULL_HASH
        new_lines: list[str] = []
        for i, data in enumerate(kept):
            data["seq"] = i + 1
            data["prev_hash"] = prev_hash
            data.pop("entry_hash", None)
            entry_hash = _hash_entry(data)
            data["entry_hash"] = entry_hash
            prev_hash = entry_hash
            new_lines.append(json.dumps(data, ensure_ascii=True))
        self._path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        self._seq = len(kept) + 1
        self._last_hash = prev_hash
        log.info("audit_log_trimmed", removed=removed, retained=len(kept))
        return removed
