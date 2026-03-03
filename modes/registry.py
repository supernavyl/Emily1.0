"""Mode registry — convenience re-exports and mode-lookup helpers.

This module exists so that external code can ``from modes.registry import ...``
without importing the engine directly.
"""

from __future__ import annotations

from modes.engine import ModeEngine, OperationalMode, get_mode_engine

__all__ = [
    "ModeEngine",
    "OperationalMode",
    "get_mode_engine",
    "get_mode",
    "list_modes",
]


def get_mode(mode_id: str) -> OperationalMode:
    """Shortcut to look up a mode by ID."""
    return get_mode_engine().get(mode_id)


def list_modes() -> dict[str, OperationalMode]:
    """Shortcut to list all modes."""
    return get_mode_engine().list_all()
