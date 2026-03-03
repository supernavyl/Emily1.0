"""
File system watcher for Emily's RAG pipeline.

Monitors configured directories for new and modified files.
When a supported file is created or modified, it is automatically
queued for ingestion into the RAG pipeline.

Uses watchdog for cross-platform file system events.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from config import RAGConfig
from observability.logger import get_logger

log = get_logger(__name__)


class RAGFileWatcher:
    """
    Watchdog-based file system monitor for auto-ingestion.

    Watches the directories configured in config.yaml under rag.watch_dirs.
    New and modified files are queued for ingestion via the provided callback.
    """

    def __init__(
        self,
        config: RAGConfig,
        on_file_change: Any,  # async callable(path: str) -> None
    ) -> None:
        """
        Args:
            config: RAG configuration with watch_dirs.
            on_file_change: Async callback invoked with the changed file path.
        """
        self._config = config
        self._callback = on_file_change
        self._observer: object | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Start the file system observer."""
        self._loop = asyncio.get_running_loop()
        try:
            from watchdog.events import FileSystemEventHandler  # type: ignore[import-untyped]
            from watchdog.observers import Observer  # type: ignore[import-untyped]

            watcher = self

            class Handler(FileSystemEventHandler):
                def on_created(self, event: Any) -> None:
                    if not event.is_directory:
                        asyncio.run_coroutine_threadsafe(
                            watcher._on_change(event.src_path),
                            watcher._loop,  # type: ignore[arg-type]
                        )

                def on_modified(self, event: Any) -> None:
                    if not event.is_directory:
                        asyncio.run_coroutine_threadsafe(
                            watcher._on_change(event.src_path),
                            watcher._loop,  # type: ignore[arg-type]
                        )

            self._observer = Observer()
            handler = Handler()

            for watch_dir in self._config.watch_dirs:
                p = Path(watch_dir)
                p.mkdir(parents=True, exist_ok=True)
                self._observer.schedule(handler, str(p), recursive=True)  # type: ignore[union-attr]
                log.info("rag_watcher_watching", directory=str(p))

            self._observer.start()  # type: ignore[union-attr]
            log.info("rag_watcher_started", dirs=self._config.watch_dirs)

        except ImportError:
            log.warning("watchdog_not_installed_rag_auto_ingest_disabled")

    async def _on_change(self, path: str) -> None:
        """Handle a file system event."""
        from rag.ingestor import _PARSER_MAP

        suffix = Path(path).suffix.lower()
        if suffix in _PARSER_MAP:
            log.info("rag_file_changed", path=path)
            await self._callback(path)

    def stop(self) -> None:
        """Stop the file system observer."""
        if self._observer:
            self._observer.stop()  # type: ignore[union-attr]
            self._observer.join()  # type: ignore[union-attr]
        log.info("rag_watcher_stopped")
