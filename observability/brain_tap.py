"""
structlog processor that mirrors log events to the BrainEventHub.

Installed as a pre-chain processor in ``configure_logging`` when the
Brain Dashboard GUI is active.  In headless mode this module is never
imported, so it has zero overhead.
"""

from __future__ import annotations

import threading
from typing import Any

_NOISY_EVENTS: set[str] = {
    "screen_capture_error",
    "perception_event_published",
}
_seen_noisy: set[str] = set()
_seen_lock = threading.Lock()

_MAX_PAYLOAD_KEYS = 10


def brain_tap_processor(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    structlog processor that forwards log events to the BrainEventHub.

    Skips noisy repeated events after their first occurrence.

    Args:
        logger: The wrapped logger object (unused).
        method_name: Log level method name (e.g. "info", "warning").
        event_dict: The structured log event dictionary.

    Returns:
        The unmodified event_dict (pass-through).
    """
    from core.brain_hub import get_brain_hub

    hub = get_brain_hub()
    if hub is None:
        return event_dict

    event_name = event_dict.get("event", "")

    if event_name in _NOISY_EVENTS:
        with _seen_lock:
            if event_name in _seen_noisy:
                return event_dict
            _seen_noisy.add(event_name)

    payload: dict[str, Any] = {
        "event": event_name,
        "level": event_dict.get("level", method_name),
        "logger": event_dict.get("logger", ""),
    }

    extra_keys = 0
    for key, value in event_dict.items():
        if key in ("event", "level", "logger", "timestamp", "_record"):
            continue
        if extra_keys >= _MAX_PAYLOAD_KEYS:
            break
        try:
            payload[key] = str(value) if not isinstance(value, (str, int, float, bool)) else value
        except Exception:
            payload[key] = "<unserializable>"
        extra_keys += 1

    hub.emit_sync("log", event_dict.get("level", method_name), payload)
    return event_dict
