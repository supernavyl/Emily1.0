"""Discord messaging tool — send messages via bot token or webhook.

Supports two modes:
1. **Webhook mode** — Simple, no bot token needed. Just a Discord webhook URL.
2. **Bot mode** — Uses a bot token to send to any channel by ID.
"""

from __future__ import annotations

import time
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult


class DiscordTool(BaseTool):
    """Send messages to Discord channels via webhook URL or bot token."""

    name = "discord"
    description = (
        "Send a message to a Discord channel. "
        "Supports webhook URLs (simple) and bot token + channel ID (flexible)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message text to send (supports Discord markdown).",
            },
            "webhook_url": {
                "type": "string",
                "description": "Discord webhook URL. Use this OR bot_token+channel_id.",
            },
            "channel_id": {
                "type": "string",
                "description": "Discord channel ID (requires bot_token in config).",
            },
            "embed": {
                "type": "object",
                "description": "Optional Discord embed object (title, description, color, fields).",
            },
            "username": {
                "type": "string",
                "description": "Override the webhook username (webhook mode only).",
                "default": "Emily",
            },
        },
        "required": ["message"],
    }
    requires_approval = True
    timeout_seconds = 15

    def __init__(self, bot_token: str = "", default_channel_id: str = "") -> None:
        self._bot_token = bot_token
        self._default_channel_id = default_channel_id

    async def dry_run(self, params: dict[str, Any]) -> str:
        msg = (params.get("message") or "")[:80]
        if params.get("webhook_url"):
            return f'Will send to Discord webhook: "{msg}..."'
        channel = params.get("channel_id") or self._default_channel_id
        return f'Will send to Discord channel {channel}: "{msg}..."'

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            import httpx  # noqa: F401
        except ImportError:
            return ToolResult.fail("httpx is required. Run: uv pip install httpx")

        message: str = params["message"]
        webhook_url: str | None = params.get("webhook_url")
        channel_id: str = params.get("channel_id") or self._default_channel_id
        embed: dict[str, Any] | None = params.get("embed")
        username: str = params.get("username", "Emily")

        if webhook_url:
            return await self._send_webhook(webhook_url, message, embed, username)
        if self._bot_token and channel_id:
            return await self._send_bot(channel_id, message, embed)
        return ToolResult.fail("Provide either a webhook_url, or configure bot_token + channel_id.")

    async def _send_webhook(
        self,
        url: str,
        message: str,
        embed: dict[str, Any] | None,
        username: str,
    ) -> ToolResult:
        import httpx

        payload: dict[str, Any] = {"content": message, "username": username}
        if embed:
            payload["embeds"] = [embed]

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
            elapsed = (time.monotonic() - t0) * 1000

            if resp.status_code in (200, 204):
                return ToolResult.ok(
                    f"Discord webhook sent ({elapsed:.0f}ms)",
                    execution_time_ms=elapsed,
                )
            return ToolResult.fail(
                f"Discord webhook returned {resp.status_code}: {resp.text[:300]}"
            )
        except Exception as exc:
            return ToolResult.fail(f"Discord webhook error: {exc}")

    async def _send_bot(
        self,
        channel_id: str,
        message: str,
        embed: dict[str, Any] | None,
    ) -> ToolResult:
        import httpx

        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self._bot_token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"content": message}
        if embed:
            payload["embeds"] = [embed]

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers)
            elapsed = (time.monotonic() - t0) * 1000

            if resp.is_success:
                return ToolResult.ok(
                    f"Discord message sent to channel {channel_id} ({elapsed:.0f}ms)",
                    execution_time_ms=elapsed,
                )
            return ToolResult.fail(f"Discord API {resp.status_code}: {resp.text[:300]}")
        except Exception as exc:
            return ToolResult.fail(f"Discord bot error: {exc}")
