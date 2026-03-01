"""Trigger → Action automation engine for Emily.

A lightweight alternative to n8n / Node-RED that runs inside Emily.
Define workflows as YAML or Python: a trigger condition fires one or
more actions using Emily's tool system.

Trigger types:
- **schedule** — cron-like (every N minutes, daily at HH:MM)
- **event** — react to internal Emily events (new_message, alert, fsm_state_change)
- **webhook** — fired when an external service POSTs to Emily's inbound webhook

Actions use the PluginRegistry — any registered tool can be an action target.

Usage::

    engine = AutomationEngine(plugin_registry=registry, fleet=fleet)
    engine.add_workflow(Workflow(
        name="morning-briefing",
        trigger=Trigger(kind=TriggerKind.SCHEDULE, config={"cron": "0 8 * * *"}),
        actions=[
            Action(tool="web_search", params={"query": "today's top news"}),
            Action(tool="discord", params={"message": "{prev_output}", "webhook_url": "..."}),
        ],
    ))
    await engine.start()
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class TriggerKind(Enum):
    """Types of triggers that can start a workflow."""

    SCHEDULE = auto()  # Time-based: interval or cron expression
    EVENT = auto()  # Internal Emily event
    WEBHOOK = auto()  # Inbound HTTP POST from external service


@dataclass
class Trigger:
    """Defines when a workflow should fire."""

    kind: TriggerKind
    config: dict[str, Any] = field(default_factory=dict)
    # SCHEDULE config: {"interval_seconds": 300} or {"cron": "0 8 * * *"}
    # EVENT config: {"event_name": "new_message", "filter": {...}}
    # WEBHOOK config: {"path": "/hooks/my-workflow", "secret": "..."}


@dataclass
class Action:
    """A single step in a workflow — executes a registered tool."""

    tool: str  # Tool name from PluginRegistry
    params: dict[str, Any] = field(default_factory=dict)  # Supports {prev_output} substitution
    on_fail: str = "stop"  # stop | continue | retry


@dataclass
class Workflow:
    """A complete automation: trigger → sequence of actions."""

    name: str
    trigger: Trigger
    actions: list[Action]
    enabled: bool = True
    description: str = ""


@dataclass
class WorkflowRun:
    """Record of a single workflow execution."""

    workflow_name: str
    started_at: float
    finished_at: float = 0.0
    success: bool = True
    action_outputs: list[str] = field(default_factory=list)
    error: str | None = None


class AutomationEngine:
    """Manages and executes automation workflows.

    Workflows are registered at startup (from config or API) and executed
    based on their trigger conditions.
    """

    def __init__(
        self,
        plugin_registry: Any,  # PluginRegistry
        fleet: Any | None = None,  # LLMFleet for AI-powered actions
    ) -> None:
        self._registry = plugin_registry
        self._fleet = fleet
        self._workflows: dict[str, Workflow] = {}
        self._schedule_tasks: dict[str, asyncio.Task[None]] = {}
        self._history: list[WorkflowRun] = []
        self._max_history = 100
        self._event_handlers: dict[str, list[str]] = {}  # event_name → [workflow_names]
        self._running = False

    def add_workflow(self, workflow: Workflow) -> None:
        """Register a new workflow."""
        self._workflows[workflow.name] = workflow
        if workflow.trigger.kind == TriggerKind.EVENT:
            event_name = workflow.trigger.config.get("event_name", "")
            if event_name:
                self._event_handlers.setdefault(event_name, []).append(workflow.name)
        log.info("workflow_added", name=workflow.name, trigger=workflow.trigger.kind.name)

    def remove_workflow(self, name: str) -> bool:
        """Remove a workflow by name."""
        wf = self._workflows.pop(name, None)
        if wf is None:
            return False
        # Cancel its schedule task if running
        task = self._schedule_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
        # Remove event handler references
        for names in self._event_handlers.values():
            if name in names:
                names.remove(name)
        log.info("workflow_removed", name=name)
        return True

    def list_workflows(self) -> list[dict[str, Any]]:
        """Return summary of all registered workflows."""
        return [
            {
                "name": wf.name,
                "trigger": wf.trigger.kind.name,
                "actions": [a.tool for a in wf.actions],
                "enabled": wf.enabled,
                "description": wf.description,
            }
            for wf in self._workflows.values()
        ]

    async def start(self) -> None:
        """Start all schedule-based workflows."""
        self._running = True
        for name, wf in self._workflows.items():
            if wf.enabled and wf.trigger.kind == TriggerKind.SCHEDULE:
                self._schedule_tasks[name] = asyncio.create_task(
                    self._schedule_loop(wf),
                    name=f"automation:{name}",
                )
        log.info("automation_engine_started", n_workflows=len(self._workflows))

    async def stop(self) -> None:
        """Stop all running schedule tasks."""
        self._running = False
        for task in self._schedule_tasks.values():
            if not task.done():
                task.cancel()
        self._schedule_tasks.clear()
        log.info("automation_engine_stopped")

    async def fire_event(self, event_name: str, data: dict[str, Any] | None = None) -> None:
        """Fire an internal event, triggering any matching workflows."""
        workflow_names = self._event_handlers.get(event_name, [])
        if not workflow_names:
            return

        log.info("event_fired", event=event_name, n_workflows=len(workflow_names))
        for name in workflow_names:
            wf = self._workflows.get(name)
            if wf and wf.enabled:
                # Pass event data as variables for action param substitution
                asyncio.create_task(self._execute_workflow(wf, extra_vars=data or {}))

    async def fire_webhook(self, path: str, payload: dict[str, Any]) -> WorkflowRun | None:
        """Fire a workflow by its webhook path. Returns the run result."""
        for wf in self._workflows.values():
            if (
                wf.enabled
                and wf.trigger.kind == TriggerKind.WEBHOOK
                and wf.trigger.config.get("path") == path
            ):
                return await self._execute_workflow(wf, extra_vars=payload)
        return None

    async def _schedule_loop(self, workflow: Workflow) -> None:
        """Run a workflow on a schedule until cancelled."""
        interval = workflow.trigger.config.get("interval_seconds", 300)
        log.info("schedule_started", workflow=workflow.name, interval_s=interval)

        while self._running:
            try:
                await asyncio.sleep(interval)
                if workflow.enabled:
                    await self._execute_workflow(workflow)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("schedule_error", workflow=workflow.name, error=str(exc)[:200])
                await asyncio.sleep(60)  # Back off on error

    async def _execute_workflow(
        self,
        workflow: Workflow,
        extra_vars: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        """Execute all actions in a workflow sequentially."""
        from plugins.base import ExecutionContext

        t0 = time.monotonic()
        run = WorkflowRun(workflow_name=workflow.name, started_at=t0)
        ctx = ExecutionContext(session_id=f"automation:{workflow.name}")

        prev_output = ""
        variables = extra_vars or {}

        log.info("workflow_start", name=workflow.name, n_actions=len(workflow.actions))

        for action in workflow.actions:
            tool = self._registry.get(action.tool)
            if tool is None:
                msg = f"Tool not found: {action.tool}"
                log.warning("workflow_action_skip", action=action.tool, reason=msg)
                if action.on_fail == "stop":
                    run.success = False
                    run.error = msg
                    break
                run.action_outputs.append(f"[SKIP] {msg}")
                continue

            # Substitute {prev_output} and other variables into params
            resolved_params = self._resolve_params(action.params, prev_output, variables)

            try:
                result = await tool.safe_execute(resolved_params, ctx)
                output_str = str(result.output or result.error or "")
                run.action_outputs.append(output_str)
                prev_output = output_str

                if not result.success:
                    log.warning(
                        "workflow_action_failed",
                        workflow=workflow.name,
                        action=action.tool,
                        error=result.error,
                    )
                    if action.on_fail == "stop":
                        run.success = False
                        run.error = result.error
                        break
            except Exception as exc:
                log.error("workflow_action_error", action=action.tool, error=str(exc)[:200])
                if action.on_fail == "stop":
                    run.success = False
                    run.error = str(exc)
                    break
                run.action_outputs.append(f"[ERROR] {exc}")

        run.finished_at = time.monotonic()
        elapsed_ms = (run.finished_at - t0) * 1000
        log.info(
            "workflow_complete",
            name=workflow.name,
            success=run.success,
            elapsed_ms=f"{elapsed_ms:.0f}",
        )

        self._history.append(run)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        return run

    @staticmethod
    def _resolve_params(
        params: dict[str, Any],
        prev_output: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """Substitute {prev_output} and {var_name} placeholders in string params."""
        resolved: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str):
                value = value.replace("{prev_output}", prev_output)
                for var_name, var_val in variables.items():
                    value = value.replace(f"{{{var_name}}}", str(var_val))
            resolved[key] = value
        return resolved

    @property
    def history(self) -> list[WorkflowRun]:
        return list(self._history)
