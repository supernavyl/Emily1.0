"""Built-in calendar reader for local iCal/JSON task files."""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult


class CalendarTool(BaseTool):
    """Read events and tasks from local iCal (.ics) or JSON task files."""

    name = "calendar_reader"
    description = (
        "Read upcoming events and tasks from local calendar files (.ics or .json). "
        "Supports filtering by date range and category."
    )
    parameters = {
        "type": "object",
        "properties": {
            "calendar_path": {
                "type": "string",
                "description": "Path to the .ics or .json calendar/task file.",
            },
            "days_ahead": {
                "type": "integer",
                "description": "Number of days ahead to look. Default: 7.",
                "default": 7,
            },
        },
        "required": ["calendar_path"],
    }
    requires_approval = False
    timeout_seconds = 5

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will read calendar file: {params.get('calendar_path', '')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Read a calendar file and return upcoming events.

        Args:
            params: Contains "calendar_path" and optional "days_ahead".
            context: Execution context.

        Returns:
            ToolResult with list of event dicts.
        """
        path = Path(params["calendar_path"])
        days = int(params.get("days_ahead", 7))

        if not path.exists():
            return ToolResult.fail(f"Calendar file not found: {path}")

        suffix = path.suffix.lower()

        if suffix == ".json":
            return self._read_json(path)
        elif suffix == ".ics":
            return await self._read_ics(path, days)
        else:
            return ToolResult.fail(f"Unsupported calendar format: {suffix}. Use .ics or .json")

    def _read_json(self, path: Path) -> ToolResult:
        """Read a simple JSON task list."""
        try:
            tasks = json.loads(path.read_text(encoding="utf-8"))
            return ToolResult.ok(tasks, format="json")
        except Exception as exc:
            return ToolResult.fail(f"JSON parse error: {exc}")

    async def _read_ics(self, path: Path, days_ahead: int) -> ToolResult:
        """Read and parse an iCal file."""
        try:
            import asyncio
            from datetime import datetime, timedelta

            import icalendar  # type: ignore[import-untyped]

            def _parse() -> list[dict[str, str]]:
                cal = icalendar.Calendar.from_ical(path.read_bytes())
                now = datetime.now(tz=UTC)
                cutoff = now + timedelta(days=days_ahead)
                events = []
                for component in cal.walk():
                    if component.name == "VEVENT":
                        dtstart = component.get("dtstart")
                        if dtstart:
                            start = dtstart.dt
                            if hasattr(start, "tzinfo") and start.tzinfo is None:
                                start = start.replace(tzinfo=UTC)
                            if now.date() <= start.date() <= cutoff.date():
                                events.append(
                                    {
                                        "summary": str(component.get("summary", "")),
                                        "start": str(start),
                                        "end": str(
                                            component.get("dtend", {}).dt
                                            if component.get("dtend")
                                            else ""
                                        ),
                                        "location": str(component.get("location", "")),
                                        "description": str(component.get("description", ""))[:200],
                                    }
                                )
                return sorted(events, key=lambda e: e["start"])

            events = await asyncio.to_thread(_parse)
            return ToolResult.ok(events, format="ics", days_ahead=days_ahead)
        except ImportError:
            return ToolResult.fail("icalendar library not installed. Run: pip install icalendar")
        except Exception as exc:
            return ToolResult.fail(f"iCal parse error: {exc}")
