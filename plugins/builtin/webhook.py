"""Outbound webhook tool — POST JSON payloads to arbitrary endpoints.

Supports n8n, Make.com, Zapier, Home Assistant, and any REST webhook.
"""

from __future__ import annotations

import time
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult

_DEFAULT_TIMEOUT = 15


class WebhookTool(BaseTool):
    """Send a JSON payload to a webhook URL via HTTP POST."""

    name = "webhook"
    description = (
        "Send a JSON payload to a webhook URL via HTTP POST. "
        "Works with n8n, Zapier, Make.com, Home Assistant webhooks, and any REST endpoint."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full webhook URL to POST to.",
            },
            "payload": {
                "type": "object",
                "description": "JSON payload to send in the request body.",
            },
            "headers": {
                "type": "object",
                "description": "Optional extra HTTP headers (e.g. Authorization).",
            },
            "method": {
                "type": "string",
                "description": "HTTP method: POST (default), PUT, PATCH.",
                "default": "POST",
            },
        },
        "required": ["url", "payload"],
    }
    requires_approval = True  # Outbound requests need user consent
    timeout_seconds = 20

    async def dry_run(self, params: dict[str, Any]) -> str:
        method = params.get("method", "POST").upper()
        url = params.get("url", "?")
        keys = list((params.get("payload") or {}).keys())
        return f"Will {method} to {url} with payload keys: {keys}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
            import httpx
        except ImportError:
            return ToolResult.fail("httpx is required for webhooks. Run: uv pip install httpx")

        url: str = params["url"]
        payload: dict[str, Any] = params["payload"]
        extra_headers: dict[str, str] = params.get("headers") or {}
        method: str = params.get("method", "POST").upper()

        if method not in {"POST", "PUT", "PATCH"}:
            return ToolResult.fail(f"Unsupported HTTP method: {method}")

        headers = {"Content-Type": "application/json", **extra_headers}

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.request(method, url, json=payload, headers=headers)

            elapsed = (time.monotonic() - t0) * 1000
            body_preview = resp.text[:500] if resp.text else ""

            if resp.is_success:
                return ToolResult.ok(
                    f"{method} {url} -> {resp.status_code} ({elapsed:.0f}ms)\n{body_preview}",
                    execution_time_ms=elapsed,
                    status_code=resp.status_code,
                )
            return ToolResult.fail(f"{method} {url} -> {resp.status_code}: {body_preview}")
        except httpx.TimeoutException:
            return ToolResult.fail(f"Webhook timed out after {_DEFAULT_TIMEOUT}s: {url}")
        except Exception as exc:
            return ToolResult.fail(f"Webhook failed: {exc}")
