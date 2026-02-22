"""
Desktop application settings with JSON persistence.

Settings are stored in ~/.emily-chat/settings.json and loaded at startup.
This is separate from the main Emily config.yaml to avoid conflicts.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


_SETTINGS_DIR = Path.home() / ".emily-chat"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"


class AppSettings(BaseModel):
    """Persisted desktop application state."""

    window_x: int = 100
    window_y: int = 100
    window_width: int = 1440
    window_height: int = 900
    maximized: bool = False
    theme: str = "dark"
    font_size: int = 14
    left_panel_width: int = 260
    right_panel_width: int = 320
    right_panel_visible: bool = True
    last_conversation_id: str | None = None
    sidebar_collapsed_groups: list[str] = []
    default_model: str = "auto"
    active_skill_id: str = "normal"
    active_profile_id: str = "default"

    @classmethod
    def load(cls) -> AppSettings:
        """Load settings from disk, returning defaults if the file is missing or corrupt."""
        if _SETTINGS_FILE.exists():
            try:
                raw = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
                return cls.model_validate(raw)
            except (json.JSONDecodeError, ValueError):
                pass
        return cls()

    def save(self) -> None:
        """Persist current settings to disk."""
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            self.model_dump_json(indent=2),
            encoding="utf-8",
        )
