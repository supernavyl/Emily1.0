"""Built-in web fetch tool — fetch and clean text from URLs."""

from __future__ import annotations

import re
from typing import Any

import httpx

from plugins.base import BaseTool, ExecutionContext, ToolResult


class WebFetchTool(BaseTool):
    """
    Fetch a URL and return clean readable text content.

    Uses a simple HTML tag stripper to extract text. For production
    quality extraction, integrate readability-lxml or trafilatura.
    """

    name = "web_fetch"
    description = (
        "Fetch the content of a URL and return clean readable text. "
        "Strips HTML tags and returns the main text content."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch."},
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return. Default: 8000.",
                "default": 8000,
            },
        },
        "required": ["url"],
    }
    requires_approval = False
    timeout_seconds = 20

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; Emily/1.0; +local)",
        "Accept": "text/html,application/xhtml+xml",
    }

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will fetch URL: {params.get('url', '')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Fetch a URL and return extracted text.

        Args:
            params: Contains "url" and optional "max_chars".
            context: Execution context.

        Returns:
            ToolResult with the extracted text content.
        """
        url = params["url"]
        max_chars = int(params.get("max_chars", 8000))

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                headers=self._HEADERS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

            if "html" in content_type:
                text = self._extract_text(resp.text)
            else:
                text = resp.text

            text = text[:max_chars]
            return ToolResult.ok(text, url=url, content_type=content_type)

        except httpx.HTTPStatusError as exc:
            return ToolResult.fail(f"HTTP {exc.response.status_code}: {url}")
        except Exception as exc:
            return ToolResult.fail(str(exc))

    @staticmethod
    def _extract_text(html: str) -> str:
        """
        Strip HTML tags and clean whitespace from HTML content.

        Args:
            html: Raw HTML string.

        Returns:
            Cleaned plain text.
        """
        # Remove script and style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.I)
        # Remove all remaining tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text
