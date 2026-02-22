"""Built-in email reader for local Maildir/MBOX files (offline)."""

from __future__ import annotations

import asyncio
import email
import mailbox
from pathlib import Path
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult


class EmailReaderTool(BaseTool):
    """
    Read emails from a local Maildir or MBOX file (fully offline).

    No IMAP/POP3 — reads directly from local mail storage files.
    """

    name = "email_reader"
    description = (
        "Read emails from a local Maildir directory or MBOX file. "
        "Fully offline — no network connection required."
    )
    parameters = {
        "type": "object",
        "properties": {
            "mailbox_path": {
                "type": "string",
                "description": "Path to Maildir directory or .mbox file.",
            },
            "max_messages": {
                "type": "integer",
                "description": "Maximum number of messages to return. Default: 10.",
                "default": 10,
            },
            "folder": {
                "type": "string",
                "description": "Maildir subfolder (e.g., 'INBOX'). Ignored for MBOX.",
                "default": "",
            },
        },
        "required": ["mailbox_path"],
    }
    requires_approval = False
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will read emails from: {params.get('mailbox_path', '')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Read messages from a local mailbox.

        Args:
            params: Contains "mailbox_path" and optional parameters.
            context: Execution context.

        Returns:
            ToolResult with list of email summary dicts.
        """
        path = Path(params["mailbox_path"])
        max_msgs = int(params.get("max_messages", 10))
        folder = params.get("folder", "")

        if not path.exists():
            return ToolResult.fail(f"Mailbox not found: {path}")

        def _read() -> list[dict[str, str]]:
            messages = []
            if path.is_dir():
                # Maildir
                mbox = mailbox.Maildir(str(path), create=False)
                if folder:
                    mbox = mbox.get_folder(folder) if folder in mbox.list_folders() else mbox
            else:
                # MBOX
                mbox = mailbox.mbox(str(path))

            for key in list(mbox.keys())[-max_msgs:]:
                try:
                    msg = mbox[key]
                    messages.append({
                        "from": msg.get("From", ""),
                        "to": msg.get("To", ""),
                        "subject": msg.get("Subject", ""),
                        "date": msg.get("Date", ""),
                        "snippet": _get_body_snippet(msg),
                    })
                except Exception:
                    continue
            return list(reversed(messages))

        try:
            messages = await asyncio.to_thread(_read)
            return ToolResult.ok(messages, count=len(messages))
        except Exception as exc:
            return ToolResult.fail(str(exc))


def _get_body_snippet(msg: email.message.Message, max_chars: int = 200) -> str:
    """Extract a short text snippet from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True)
                if body:
                    return body.decode(errors="replace")[:max_chars]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(errors="replace")[:max_chars]
    return ""
