"""
Persistent event recorder for Emily's Agent Replay Debugger.

Subscribes to BrainEventHub and writes every event to an append-only JSONL
file at ``data/replay/{session_id}.jsonl``.  Old session files are
compressed with gzip after a configurable delay.

Each line has the shape:
    {"ts": float, "cat": str, "kind": str, "data": dict, "seq": int}

The ``seq`` field is a monotonically increasing integer that guarantees
total ordering even if wall-clock timestamps collide.

Usage:
    recorder = EventRecorder(config)
    recorder.attach(brain_hub)       # hooks into hub.emit_sync
    recorder.start_session()          # opens a new JSONL file
    ...
    recorder.end_session()            # flushes and closes
    recorder.compress_old_sessions()  # gzip anything older than threshold
"""

from __future__ import annotations

import gzip
import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_DEFAULT_REPLAY_DIR = Path("data/replay")


class EventRecorder:
    """Append-only JSONL recorder attached to :class:`BrainEventHub`.

    Thread-safe: the write path is guarded by a lock so that
    ``emit_sync`` (called from any thread) can safely record.
    """

    def __init__(
        self,
        replay_dir: str | Path = _DEFAULT_REPLAY_DIR,
        compress_after_hours: float = 24.0,
        enabled: bool = True,
    ) -> None:
        self._replay_dir = Path(replay_dir)
        self._compress_after_hours = compress_after_hours
        self._enabled = enabled

        self._session_id: str | None = None
        self._file: Any | None = None  # typing: IO[str]
        self._seq = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def attach(self, brain_hub: Any) -> None:
        """Register as a persistent recorder on *brain_hub*.

        The hub calls ``_on_event`` synchronously for every event (including
        rate-limited log events that passed the hub's own filter).
        """
        if not self._enabled:
            return
        brain_hub.attach_recorder(self._on_event)
        log.info("event_recorder_attached")

    def start_session(self, session_id: str | None = None) -> str:
        """Open a new JSONL file for the given (or generated) session.

        Returns the session id.
        """
        if not self._enabled:
            return session_id or str(uuid.uuid4())

        sid = session_id or str(uuid.uuid4())
        self._replay_dir.mkdir(parents=True, exist_ok=True)
        path = self._replay_dir / f"{sid}.jsonl"

        with self._lock:
            self._flush_and_close()
            self._session_id = sid
            self._seq = 0
            self._file = path.open("a", encoding="utf-8")

        log.info("event_recorder_session_started", session_id=sid, path=str(path))
        return sid

    def end_session(self) -> None:
        """Flush and close the current session file."""
        with self._lock:
            self._flush_and_close()
            self._session_id = None
        log.info("event_recorder_session_ended")

    def close(self) -> None:
        """Alias for :meth:`end_session`."""
        self.end_session()

    # ------------------------------------------------------------------
    # Recording callback
    # ------------------------------------------------------------------

    def _on_event(self, event: dict[str, Any]) -> None:
        """Callback invoked by BrainEventHub.emit_sync for every event."""
        with self._lock:
            if self._file is None:
                return
            self._seq += 1
            record = {
                "ts": event.get("ts", time.time()),
                "cat": event.get("cat", ""),
                "kind": event.get("kind", ""),
                "data": event.get("data", {}),
                "seq": self._seq,
            }
            try:
                self._file.write(json.dumps(record, default=str) + "\n")
                self._file.flush()
            except Exception as exc:
                log.error("event_recorder_write_error", error=str(exc))

    # ------------------------------------------------------------------
    # AgentBus full-payload recording
    # ------------------------------------------------------------------

    def record_bus_message(self, direction: str, message_dict: dict[str, Any]) -> None:
        """Record a full AgentBus message payload.

        Called from ``AgentBus.send()`` (direction="send") and
        ``AgentBus._receive_loop()`` (direction="recv").

        This creates a dedicated ``bus`` category event so replay can
        reconstruct the full message flow including payloads (the hub
        only sees a summary).
        """
        with self._lock:
            if self._file is None:
                return
            self._seq += 1
            record = {
                "ts": time.time(),
                "cat": "bus",
                "kind": direction,
                "data": message_dict,
                "seq": self._seq,
            }
            try:
                self._file.write(json.dumps(record, default=str) + "\n")
                self._file.flush()
            except Exception as exc:
                log.error("event_recorder_bus_write_error", error=str(exc))

    # ------------------------------------------------------------------
    # Compression of old sessions
    # ------------------------------------------------------------------

    def compress_old_sessions(self) -> int:
        """Gzip session files older than ``compress_after_hours``.

        Returns the number of files compressed.
        """
        if not self._replay_dir.exists():
            return 0

        threshold = time.time() - self._compress_after_hours * 3600
        compressed = 0

        for path in self._replay_dir.glob("*.jsonl"):
            # Skip the active session
            if self._session_id and path.stem == self._session_id:
                continue
            if path.stat().st_mtime < threshold:
                gz_path = path.with_suffix(".jsonl.gz")
                try:
                    with path.open("rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                    path.unlink()
                    compressed += 1
                except Exception as exc:
                    log.warning("event_recorder_compress_error", path=str(path), error=str(exc))

        if compressed:
            log.info("event_recorder_compressed_sessions", count=compressed)
        return compressed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _flush_and_close(self) -> None:
        """Flush and close the file handle (caller must hold ``_lock``)."""
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except Exception:
                pass
            self._file = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def event_count(self) -> int:
        return self._seq
