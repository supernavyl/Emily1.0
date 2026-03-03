"""Built-in process manager tool. Requires approval for kill operations."""

from __future__ import annotations

import asyncio
from typing import Any

import psutil

from plugins.base import BaseTool, ExecutionContext, ToolResult


class ProcessManagerTool(BaseTool):
    """
    List and manage system processes.

    List and inspect operations do not require approval.
    Kill operations require explicit user approval.
    """

    name = "process_manager"
    description = (
        "List running processes, inspect process details, or terminate processes. "
        "Kill operations REQUIRE USER APPROVAL."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Action: 'list', 'info', 'kill'.",
            },
            "pid": {
                "type": "integer",
                "description": "Process ID. Required for 'info' and 'kill'.",
            },
            "name_filter": {
                "type": "string",
                "description": "Filter processes by name (for 'list' action).",
            },
            "top_n": {
                "type": "integer",
                "description": "Return top N processes by CPU usage (for 'list'). Default: 10.",
                "default": 10,
            },
        },
        "required": ["action"],
    }
    requires_approval = False  # Overridden per-action

    async def dry_run(self, params: dict[str, Any]) -> str:
        action = params.get("action", "")
        pid = params.get("pid", "")
        if action == "kill":
            return f"Will terminate process with PID {pid} (REQUIRES APPROVAL)"
        return f"Will {action} processes"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Execute a process management action.

        Args:
            params: Contains "action" and action-specific parameters.
            context: Execution context.

        Returns:
            ToolResult with process information or action status.
        """
        action = params["action"]

        def _list_processes() -> list[dict]:
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "status"]):
                try:
                    info = p.info
                    name_filter = params.get("name_filter", "")
                    if name_filter and name_filter.lower() not in (info.get("name") or "").lower():
                        continue
                    procs.append(
                        {
                            "pid": info["pid"],
                            "name": info["name"],
                            "cpu_percent": info["cpu_percent"],
                            "memory_mb": round(
                                (info["memory_info"].rss if info["memory_info"] else 0)
                                / 1024
                                / 1024,
                                1,
                            ),
                            "status": info["status"],
                        }
                    )
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            procs.sort(key=lambda p: p["cpu_percent"] or 0, reverse=True)
            top_n = int(params.get("top_n", 10))
            return procs[:top_n]

        if action == "list":
            procs = await asyncio.to_thread(_list_processes)
            return ToolResult.ok(procs, count=len(procs))

        elif action == "info":
            pid = params.get("pid")
            if not pid:
                return ToolResult.fail("pid required for 'info' action")
            try:
                p = psutil.Process(int(pid))
                info = {
                    "pid": p.pid,
                    "name": p.name(),
                    "exe": p.exe(),
                    "cmdline": " ".join(p.cmdline()),
                    "status": p.status(),
                    "cpu_percent": p.cpu_percent(),
                    "memory_mb": round(p.memory_info().rss / 1024 / 1024, 1),
                    "create_time": p.create_time(),
                    "num_threads": p.num_threads(),
                }
                return ToolResult.ok(info)
            except psutil.NoSuchProcess:
                return ToolResult.fail(f"Process {pid} not found")
            except psutil.AccessDenied:
                return ToolResult.fail(f"Access denied for process {pid}")

        elif action == "kill":
            # Kill requires approval (enforced by consent gate in Phase 19)
            pid = params.get("pid")
            if not pid:
                return ToolResult.fail("pid required for 'kill' action")
            try:
                p = psutil.Process(int(pid))
                name = p.name()
                p.terminate()
                return ToolResult.ok(f"Process {pid} ({name}) terminated")
            except psutil.NoSuchProcess:
                return ToolResult.fail(f"Process {pid} not found")
            except psutil.AccessDenied:
                return ToolResult.fail(f"Permission denied: cannot terminate process {pid}")

        else:
            return ToolResult.fail(f"Unknown action: {action}. Use: list, info, kill")
