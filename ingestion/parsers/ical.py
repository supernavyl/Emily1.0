"""
iCalendar (.ics) parser — imports calendar events into the events table.

Parses RFC 5545 iCal files using the `icalendar` library and converts
VEVENT components into EventRecord-compatible dicts for the ingestion
coordinator to persist.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class ParsedEvent:
    """A calendar event parsed from an .ics file."""

    title: str = ""
    event_type: str = "calendar"
    datetime_str: str = ""  # ISO8601
    duration_minutes: int | None = None
    location: str = ""
    description: str = ""
    organizer: str = ""
    attendees: list[str] = field(default_factory=list)
    raw_text: str = ""


def _dt_to_iso(dt_value: Any) -> str:
    """Convert icalendar date/datetime to ISO8601 string."""
    try:
        from datetime import date as date_type
        from datetime import datetime as dt_type

        if isinstance(dt_value, dt_type):
            if dt_value.tzinfo is None:
                dt_value = dt_value.replace(tzinfo=UTC)
            return dt_value.isoformat()
        if isinstance(dt_value, date_type):
            return datetime(dt_value.year, dt_value.month, dt_value.day, tzinfo=UTC).isoformat()
    except Exception:
        pass
    return str(dt_value)


async def parse_ical_file(path: Path) -> list[ParsedEvent]:
    """
    Parse an .ics file and return a list of ParsedEvent objects.

    Args:
        path: Path to the .ics file.

    Returns:
        List of ParsedEvent objects.
    """
    content = await asyncio.to_thread(path.read_bytes)
    return await asyncio.to_thread(_parse_ical_content, content)


def _parse_ical_content(content: bytes) -> list[ParsedEvent]:
    """
    Synchronous iCal parsing worker.

    Args:
        content: Raw .ics file bytes.

    Returns:
        List of ParsedEvent objects.
    """
    try:
        from icalendar import Calendar
    except ImportError:
        log.error("icalendar_not_installed")
        return []

    events: list[ParsedEvent] = []

    try:
        cal = Calendar.from_ical(content)
        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            event = ParsedEvent()

            summary = component.get("SUMMARY")
            event.title = str(summary) if summary else "Untitled Event"

            dtstart = component.get("DTSTART")
            if dtstart:
                event.datetime_str = _dt_to_iso(dtstart.dt)

            dtend = component.get("DTEND")
            duration_prop = component.get("DURATION")
            if dtstart and dtend:
                try:
                    delta = dtend.dt - dtstart.dt
                    event.duration_minutes = int(delta.total_seconds() / 60)
                except Exception:
                    pass
            elif duration_prop:
                with contextlib.suppress(Exception):
                    event.duration_minutes = int(duration_prop.dt.total_seconds() / 60)

            location = component.get("LOCATION")
            event.location = str(location) if location else ""

            description = component.get("DESCRIPTION")
            event.description = str(description) if description else ""

            organizer = component.get("ORGANIZER")
            if organizer:
                event.organizer = str(organizer).replace("mailto:", "")

            attendees_raw = component.get("ATTENDEE", [])
            if not isinstance(attendees_raw, list):
                attendees_raw = [attendees_raw]
            event.attendees = [str(a).replace("mailto:", "") for a in attendees_raw]

            parts = [f"Event: {event.title}"]
            if event.datetime_str:
                parts.append(f"When: {event.datetime_str}")
            if event.location:
                parts.append(f"Location: {event.location}")
            if event.description:
                parts.append(f"Description: {event.description[:300]}")
            event.raw_text = "\n".join(parts)

            if event.datetime_str:
                events.append(event)

    except Exception as exc:
        log.error("ical_parse_error", error=str(exc))

    log.info("ical_parsed", count=len(events))
    return events
