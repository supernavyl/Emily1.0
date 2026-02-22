"""Built-in desktop notification tool using libnotify."""

from __future__ import annotations

import asyncio
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult


class NotificationTool(BaseTool):
    """Send desktop notifications via libnotify (notify-send)."""

    name = "notification_sender"
    description = "Send a desktop notification to the user via libnotify (notify-send)."
    parameters = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Notification title."},
            "message": {"type": "string", "description": "Notification body text."},
            "urgency": {
                "type": "string",
                "description": "Urgency level: low, normal, critical.",
                "default": "normal",
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Display timeout in ms. -1 = persistent.",
                "default": 5000,
            },
        },
        "required": ["title", "message"],
    }
    requires_approval = False
    timeout_seconds = 5

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will send desktop notification: [{params.get('title')}] {params.get('message')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Send a desktop notification.

        Args:
            params: Contains "title", "message", optional "urgency" and "timeout_ms".
            context: Execution context.

        Returns:
            ToolResult indicating if the notification was sent.
        """
        title = params["title"]
        message = params["message"]
        urgency = params.get("urgency", "normal")
        timeout_ms = int(params.get("timeout_ms", 5000))

        cmd = [
            "notify-send",
            "--urgency", urgency,
            "--expire-time", str(timeout_ms),
            "--app-name", "Emily",
            title,
            message,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode != 0:
                return ToolResult.fail(stderr.decode(errors="replace").strip())
            return ToolResult.ok(f"Notification sent: {title}")
        except FileNotFoundError:
            return ToolResult.fail("notify-send not found. Install libnotify.")
        except asyncio.TimeoutError:
            return ToolResult.fail("Notification command timed out")
        except Exception as exc:
            return ToolResult.fail(str(exc))
