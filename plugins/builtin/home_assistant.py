"""Built-in Home Assistant integration tool."""

from __future__ import annotations

from typing import Any

import httpx

from plugins.base import BaseTool, ExecutionContext, ToolResult


class HomeAssistantTool(BaseTool):
    """
    Interact with a local Home Assistant instance via its REST API.

    Read operations (get states, get entities) do not require approval.
    Write operations (call services, trigger automations) require approval.
    """

    name = "home_assistant"
    description = (
        "Interact with Home Assistant: read entity states, trigger automations, "
        "and control smart home devices. "
        "Write operations (service calls) REQUIRE USER APPROVAL."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'get_state', 'get_states', 'call_service', 'get_automations'.",
            },
            "entity_id": {
                "type": "string",
                "description": "Entity ID (e.g., 'light.living_room'). For get_state and call_service.",
            },
            "domain": {
                "type": "string",
                "description": "Service domain for call_service (e.g., 'light', 'switch').",
            },
            "service": {
                "type": "string",
                "description": "Service name for call_service (e.g., 'turn_on', 'turn_off').",
            },
            "service_data": {
                "type": "object",
                "description": "Additional data for the service call.",
            },
        },
        "required": ["action"],
    }
    requires_approval = False  # Read ops; write ops override this per-call
    timeout_seconds = 10

    def __init__(self, ha_url: str = "http://localhost:8123", token: str | None = None) -> None:
        """
        Args:
            ha_url: Home Assistant base URL.
            token: Long-lived access token.
        """
        self._url = ha_url.rstrip("/")
        self._token = token

    @property
    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    async def dry_run(self, params: dict[str, Any]) -> str:
        action = params.get("action", "")
        if action == "call_service":
            return (
                f"Will call HA service {params.get('domain', '')}.{params.get('service', '')} "
                f"on {params.get('entity_id', 'all')}"
            )
        return f"Will execute HA action: {action}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Execute a Home Assistant API call.

        Args:
            params: Contains "action" and action-specific parameters.
            context: Execution context.

        Returns:
            ToolResult with HA API response.
        """
        action = params["action"]

        if not self._token:
            return ToolResult.fail("Home Assistant token not configured. Set EMILY_TOOLS__HOME_ASSISTANT__TOKEN in .env")

        try:
            async with httpx.AsyncClient(
                base_url=self._url, headers=self._headers, timeout=self.timeout_seconds
            ) as client:
                if action == "get_state":
                    entity_id = params.get("entity_id")
                    if not entity_id:
                        return ToolResult.fail("entity_id required for get_state")
                    resp = await client.get(f"/api/states/{entity_id}")
                    resp.raise_for_status()
                    return ToolResult.ok(resp.json())

                elif action == "get_states":
                    resp = await client.get("/api/states")
                    resp.raise_for_status()
                    states = resp.json()
                    # Return just entity IDs and states for brevity
                    summary = [{"entity_id": s["entity_id"], "state": s["state"]} for s in states]
                    return ToolResult.ok(summary, total=len(states))

                elif action == "call_service":
                    domain = params.get("domain")
                    service = params.get("service")
                    if not domain or not service:
                        return ToolResult.fail("domain and service required for call_service")
                    service_data = params.get("service_data", {})
                    if params.get("entity_id"):
                        service_data["entity_id"] = params["entity_id"]
                    resp = await client.post(
                        f"/api/services/{domain}/{service}",
                        json=service_data,
                    )
                    resp.raise_for_status()
                    return ToolResult.ok(f"Service {domain}.{service} called successfully")

                elif action == "get_automations":
                    resp = await client.get("/api/config/automation/config")
                    resp.raise_for_status()
                    return ToolResult.ok(resp.json())

                else:
                    return ToolResult.fail(f"Unknown action: {action}")

        except httpx.ConnectError:
            return ToolResult.fail(f"Cannot connect to Home Assistant at {self._url}")
        except httpx.HTTPStatusError as exc:
            return ToolResult.fail(f"HA API error: {exc.response.status_code}")
        except Exception as exc:
            return ToolResult.fail(str(exc))
