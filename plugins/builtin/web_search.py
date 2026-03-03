"""Built-in web search tool using local SearXNG instance."""

from __future__ import annotations

from typing import Any

import httpx

from plugins.base import BaseTool, ExecutionContext, ToolResult


class WebSearchTool(BaseTool):
    """
    Web search via a local SearXNG instance.

    SearXNG is a self-hosted meta-search engine that aggregates results
    from multiple search engines while preserving privacy.
    """

    name = "web_search"
    description = (
        "Search the web using a local SearXNG instance. "
        "Returns a list of result titles, URLs, and snippets. "
        "Requires a running SearXNG instance (configured in config.yaml)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "num_results": {
                "type": "integer",
                "description": "Number of results to return. Default: 5.",
                "default": 5,
            },
            "language": {
                "type": "string",
                "description": "Language code for results. Default: en.",
                "default": "en",
            },
        },
        "required": ["query"],
    }
    requires_approval = False
    timeout_seconds = 15

    def __init__(self, searxng_url: str = "http://localhost:8080") -> None:
        """
        Args:
            searxng_url: Base URL of the local SearXNG instance.
        """
        self._url = searxng_url

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will search the web for: {params.get('query', '')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Execute a web search against SearXNG.

        Args:
            params: Contains "query", optional "num_results" and "language".
            context: Execution context.

        Returns:
            ToolResult with list of search result dicts.
        """
        query = params["query"]
        num = int(params.get("num_results", 5))
        lang = params.get("language", "en")

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(
                    f"{self._url}/search",
                    params={
                        "q": query,
                        "format": "json",
                        "language": lang,
                        "safesearch": "0",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for r in data.get("results", [])[:num]:
                results.append(
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                        "engine": r.get("engine", ""),
                    }
                )

            return ToolResult.ok(results, query=query, total_found=len(data.get("results", [])))

        except httpx.ConnectError:
            return ToolResult.fail(
                f"Cannot connect to SearXNG at {self._url}. Run: docker-compose up -d searxng"
            )
        except Exception as exc:
            return ToolResult.fail(str(exc))
