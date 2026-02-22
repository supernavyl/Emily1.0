"""
QSS theme engine with variable substitution.

Each .qss file uses ``@variable_name`` tokens that the engine replaces
with concrete hex values before applying the stylesheet.  This keeps
every colour definition in one place and lets themes switch instantly
without an application restart.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtWidgets import QApplication

_THEMES_DIR = Path(__file__).parent.parent / "assets" / "themes"

# Maps a theme name to its variable palette.  QSS files reference these
# via ``@name`` tokens, e.g.  ``background-color: @background;``
PALETTES: dict[str, dict[str, str]] = {
    "dark": {
        "background": "#0a0a0f",
        "surface": "#111118",
        "surface_raised": "#1a1a24",
        "border": "#2a2a3a",
        "accent": "#7c6af7",
        "accent_hover": "#9b8cf9",
        "text_primary": "#f0f0f5",
        "text_secondary": "#8888aa",
        "text_muted": "#555570",
        "thinking_bg": "#0d1520",
        "thinking_border": "#1e3a5f",
        "code_bg": "#0d0d14",
        "code_border": "#1e1e2e",
        "user_bubble": "#1a1a2e",
        "emily_bubble": "#111118",
        "cost_green": "#22c55e",
        "warning_amber": "#f59e0b",
        "error_red": "#ef4444",
        "link_color": "#8b9cf7",
        "action_btn_hover": "#252540",
        "phase_analyzing": "#3b82f6",
        "phase_considering": "#f59e0b",
        "phase_comparing": "#a855f7",
        "phase_concluding": "#22c55e",
        "phase_uncertain": "#eab308",
        "progress_bar": "#7c6af7",
        "progress_bg": "#1a1a24",
        "warning_yellow_bg": "#332800",
        "warning_red_bg": "#331111",
        "toolbar_active": "#3b82f6",
        "search_overlay_bg": "rgba(10, 10, 15, 200)",
        "search_highlight": "#f59e0b",
    },
    "light": {
        "background": "#f5f5f7",
        "surface": "#ffffff",
        "surface_raised": "#f0f0f3",
        "border": "#d8d8e0",
        "accent": "#7c6af7",
        "accent_hover": "#6554d9",
        "text_primary": "#1a1a2e",
        "text_secondary": "#555570",
        "text_muted": "#8888aa",
        "thinking_bg": "#eef2f8",
        "thinking_border": "#b8cce0",
        "code_bg": "#f0f0f4",
        "code_border": "#d0d0da",
        "user_bubble": "#e8e6f8",
        "emily_bubble": "#ffffff",
        "cost_green": "#16a34a",
        "warning_amber": "#d97706",
        "error_red": "#dc2626",
        "link_color": "#5b4fd9",
        "action_btn_hover": "#e4e4ec",
        "phase_analyzing": "#2563eb",
        "phase_considering": "#d97706",
        "phase_comparing": "#9333ea",
        "phase_concluding": "#16a34a",
        "phase_uncertain": "#ca8a04",
        "progress_bar": "#7c6af7",
        "progress_bg": "#e4e4ec",
        "warning_yellow_bg": "#fff8e1",
        "warning_red_bg": "#fce4ec",
        "toolbar_active": "#2563eb",
        "search_overlay_bg": "rgba(245, 245, 247, 200)",
        "search_highlight": "#d97706",
    },
}

_TOKEN_RE = re.compile(r"@(\w+)")


def _substitute(qss: str, palette: dict[str, str]) -> str:
    """Replace ``@token`` placeholders with values from *palette*."""
    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        return palette.get(key, m.group(0))
    return _TOKEN_RE.sub(_replace, qss)


class ThemeEngine:
    """Loads and applies QSS themes with variable substitution."""

    def __init__(self, app: QApplication) -> None:
        self._app = app
        self._current_theme: str = ""

    @property
    def current_theme(self) -> str:
        """Name of the currently applied theme."""
        return self._current_theme

    @staticmethod
    def available_themes() -> list[str]:
        """Return the names of all bundled themes."""
        return sorted(PALETTES.keys())

    def apply_theme(self, name: str) -> None:
        """Load the QSS file for *name*, substitute variables, and apply."""
        palette = PALETTES.get(name)
        if palette is None:
            palette = PALETTES["dark"]
            name = "dark"

        qss_path = _THEMES_DIR / f"{name}.qss"
        if not qss_path.exists():
            return

        raw_qss = qss_path.read_text(encoding="utf-8")
        resolved_qss = _substitute(raw_qss, palette)
        self._app.setStyleSheet(resolved_qss)
        self._current_theme = name
