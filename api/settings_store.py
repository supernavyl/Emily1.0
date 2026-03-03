"""Persistent JSON-backed settings store.

All user-editable settings (permissions, persona traits, advanced config,
tool permissions) are stored in ``data/user_settings.json``.  On first
access the store loads from disk, falling back to config.yaml defaults.
Every mutation triggers an atomic write-through (tempfile + os.replace).
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

_SETTINGS_PATH = Path("data/user_settings.json")


class SettingsStore:
    """Thread-safe, write-through JSON settings store."""

    def __init__(self, path: Path = _SETTINGS_PATH) -> None:
        self._path = path
        self._data: dict[str, Any] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
                log.info("settings_loaded_from_disk", path=str(self._path))
            except Exception as exc:
                log.warning("settings_load_failed_using_defaults", error=str(exc))
                self._data = {}
        self._loaded = True

    def get_section(self, section: str, defaults: dict[str, Any]) -> dict[str, Any]:
        """Return a settings section, merging disk data over defaults."""
        self._ensure_loaded()
        stored = self._data.get(section, {})
        merged = {**defaults, **stored}
        return merged

    def update_section(self, section: str, updates: dict[str, Any]) -> dict[str, Any]:
        """Merge updates into a section and write through to disk."""
        self._ensure_loaded()
        if section not in self._data:
            self._data[section] = {}
        self._data[section].update(updates)
        self._write()
        return self._data[section]

    def set_section(self, section: str, data: dict[str, Any]) -> None:
        """Replace an entire section and write through."""
        self._ensure_loaded()
        self._data[section] = data
        self._write()

    def get_all(self) -> dict[str, Any]:
        """Return all settings data (for export)."""
        self._ensure_loaded()
        return dict(self._data)

    def import_all(self, data: dict[str, Any]) -> None:
        """Replace all settings with imported data and write through."""
        self._data = dict(data)
        self._loaded = True
        self._write()

    def _write(self) -> None:
        """Atomic write: write to tempfile then os.replace."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self._path)
            except Exception:
                # Clean up temp file on failure
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
                raise
            log.info("settings_written", path=str(self._path))
        except Exception as exc:
            log.error("settings_write_failed", error=str(exc))


# Module-level singleton
_store: SettingsStore | None = None


def get_settings_store() -> SettingsStore:
    """Return the global SettingsStore singleton."""
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store
