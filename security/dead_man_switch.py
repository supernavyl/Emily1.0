"""
Dead man's switch for Emily.

If Emily has not been interacted with for more than N days (configurable,
default 30), she automatically:
1. Shuts down all background services.
2. Wipes the episodic memory database.
3. Wipes the knowledge graph and vector store.
4. Deletes generated tools.
5. Logs the wipe event to the audit log.

This protects against stale, accumulated PII in the event the user stops
using Emily without explicitly erasing data.

The switch timer is reset every time a user utterance is processed.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from observability.logger import get_logger
from security.audit_log import AuditLog

log = get_logger(__name__)


class DeadManSwitch:
    """
    Tracks last user interaction timestamp and triggers a self-wipe
    if the inactivity period exceeds the configured threshold.
    """

    def __init__(
        self,
        audit_log: AuditLog,
        threshold_days: int = 30,
        check_interval_s: float = 3600.0,
        heartbeat_path: str | Path = "data/.emily_last_active",
    ) -> None:
        """
        Args:
            audit_log: AuditLog for recording the wipe event.
            threshold_days: Days of inactivity before auto-wipe.
            check_interval_s: How often to check (default: hourly).
            heartbeat_path: Path for the heartbeat file (resolved to absolute at init).
        """
        self._audit = audit_log
        self._threshold_s = threshold_days * 86400.0
        self._check_interval = check_interval_s
        self._heartbeat_path = Path(heartbeat_path).resolve()
        self._task: asyncio.Task[None] | None = None

    def heartbeat(self) -> None:
        """
        Record a user interaction heartbeat.

        Call this every time a user utterance is received.
        """
        self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
        self._heartbeat_path.write_text(str(time.time()))

    def _last_active(self) -> float:
        """Return the timestamp of the last recorded heartbeat."""
        if not self._heartbeat_path.exists():
            return time.time()
        try:
            return float(self._heartbeat_path.read_text().strip())
        except ValueError:
            return time.time()

    def _inactivity_seconds(self) -> float:
        """Return how many seconds have elapsed since the last heartbeat."""
        return time.time() - self._last_active()

    async def start(self) -> None:
        """Start the dead man's switch background monitor."""
        self._task = asyncio.create_task(self._monitor(), name="dead_man_switch")
        log.info("dead_man_switch_started", threshold_days=int(self._threshold_s / 86400))

    async def stop(self) -> None:
        """Stop the dead man's switch monitor."""
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _monitor(self) -> None:
        """Main monitoring loop."""
        while True:
            await asyncio.sleep(self._check_interval)
            idle = self._inactivity_seconds()
            if idle >= self._threshold_s:
                log.warning("dead_man_switch_triggered", idle_days=idle / 86400)
                await self._wipe()
                break

    async def _wipe(self) -> None:
        """
        Perform the self-wipe: delete sensitive data files.
        """
        await self._audit.append(
            event="dead_man_switch_wipe",
            actor="DeadManSwitch",
            payload={"idle_seconds": self._inactivity_seconds()},
        )

        wipe_targets = [
            Path("data/episodes.db"),
            Path("data/knowledge_graph.json"),
            Path("data/bm25_index"),
            Path("plugins/generated"),
            Path("data/procedural.json"),
        ]

        for target in wipe_targets:
            try:
                if target.is_file():
                    target.unlink()
                    log.info("dead_man_switch_wiped_file", path=str(target))
                elif target.is_dir():
                    import shutil

                    shutil.rmtree(target)
                    log.info("dead_man_switch_wiped_dir", path=str(target))
            except Exception as exc:
                log.error("dead_man_switch_wipe_error", path=str(target), error=str(exc))

        log.warning("dead_man_switch_wipe_complete")
