"""Inbound integration API routes.

Provides endpoints for:
- External webhooks (n8n, Zapier, Make.com can POST here)
- Crew execution (kick off multi-agent tasks via API)
- Automation workflow management (CRUD + manual trigger)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

# These get set by bootstrap / app wiring
_automation_engine: Any = None
_fleet: Any = None
_plugin_registry: Any = None


def configure(
    automation_engine: Any = None,
    fleet: Any = None,
    plugin_registry: Any = None,
) -> None:
    """Wire runtime dependencies. Called during app startup."""
    global _automation_engine, _fleet, _plugin_registry
    _automation_engine = automation_engine
    _fleet = fleet
    _plugin_registry = plugin_registry


# ── Inbound Webhooks ─────────────────────────────────────────────────


class WebhookPayload(BaseModel):
    """Generic inbound webhook payload."""

    data: dict[str, Any] = Field(default_factory=dict)
    source: str = ""


@router.post("/webhook/{path:path}")
async def inbound_webhook(path: str, payload: WebhookPayload) -> dict[str, Any]:
    """Receive a webhook from an external service and route to matching workflow.

    Example: n8n sends POST to /api/v1/integrations/webhook/daily-summary
    and the automation engine fires the workflow with trigger path "daily-summary".
    """
    if _automation_engine is None:
        raise HTTPException(503, "Automation engine not initialized")

    full_path = f"/hooks/{path}"
    run = await _automation_engine.fire_webhook(full_path, payload.data)
    if run is None:
        raise HTTPException(404, f"No workflow registered for webhook path: {full_path}")

    return {
        "workflow": run.workflow_name,
        "success": run.success,
        "outputs": run.action_outputs,
        "error": run.error,
    }


# ── Event Firing ─────────────────────────────────────────────────────


class EventPayload(BaseModel):
    """Fire an internal Emily event."""

    event_name: str
    data: dict[str, Any] = Field(default_factory=dict)


@router.post("/events/fire")
async def fire_event(payload: EventPayload) -> dict[str, str]:
    """Fire an internal event that triggers matching automation workflows."""
    if _automation_engine is None:
        raise HTTPException(503, "Automation engine not initialized")

    await _automation_engine.fire_event(payload.event_name, payload.data)
    return {"status": "fired", "event": payload.event_name}


# ── Crew Execution ───────────────────────────────────────────────────


class CrewRequest(BaseModel):
    """Kick off a crew (multi-agent task)."""

    crew_name: str = ""
    agents: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    mode: str = "sequential"  # sequential | parallel


@router.post("/crews/run")
async def run_crew(req: CrewRequest) -> dict[str, Any]:
    """Execute a crew of agents on a set of tasks.

    Either provide a pre-built crew_name or define agents+tasks inline.
    """
    if _fleet is None:
        raise HTTPException(503, "LLM fleet not initialized")

    from integrations.crews import (
        Crew,
        CrewAgent,
        CrewTask,
        ExecutionMode,
    )

    if not req.agents or not req.tasks:
        raise HTTPException(400, "Provide at least one agent and one task")

    agents = [
        CrewAgent(
            role=a.get("role", "Assistant"),
            goal=a.get("goal", "Help the user"),
            backstory=a.get("backstory", ""),
            llm_tier=a.get("llm_tier", "smart"),
            tools=a.get("tools", []),
        )
        for a in req.agents
    ]

    tasks = [
        CrewTask(
            description=t["description"],
            agent=agents[t.get("agent_index", 0)],
            expected_output=t.get("expected_output", ""),
        )
        for t in req.tasks
    ]

    mode = ExecutionMode.PARALLEL if req.mode == "parallel" else ExecutionMode.SEQUENTIAL

    crew = Crew(
        agents=agents,
        tasks=tasks,
        fleet=_fleet,
        plugin_registry=_plugin_registry,
        mode=mode,
    )

    result = await crew.kickoff(**req.variables)

    return {
        "success": result.success,
        "final_output": result.final_output,
        "total_latency_ms": round(result.total_latency_ms),
        "task_results": [
            {
                "task_id": tr.task_id,
                "agent": tr.agent_role,
                "model": tr.model_used,
                "output": tr.output[:2000],  # Truncate for API response
                "success": tr.success,
                "latency_ms": round(tr.latency_ms),
            }
            for tr in result.task_results
        ],
    }


# ── Automation Workflow Management ───────────────────────────────────


@router.get("/workflows")
async def list_workflows() -> list[dict[str, Any]]:
    """List all registered automation workflows."""
    if _automation_engine is None:
        return []
    return _automation_engine.list_workflows()


class WorkflowDef(BaseModel):
    """Define a workflow via API."""

    name: str
    trigger_kind: str  # schedule | event | webhook
    trigger_config: dict[str, Any] = Field(default_factory=dict)
    actions: list[dict[str, Any]]  # [{tool: "...", params: {...}, on_fail: "stop"}]
    description: str = ""
    enabled: bool = True


@router.post("/workflows")
async def create_workflow(wf: WorkflowDef) -> dict[str, str]:
    """Create a new automation workflow at runtime."""
    if _automation_engine is None:
        raise HTTPException(503, "Automation engine not initialized")

    from integrations.automation import Action, Trigger, TriggerKind, Workflow

    kind_map = {
        "schedule": TriggerKind.SCHEDULE,
        "event": TriggerKind.EVENT,
        "webhook": TriggerKind.WEBHOOK,
    }
    trigger_kind = kind_map.get(wf.trigger_kind.lower())
    if trigger_kind is None:
        raise HTTPException(400, f"Invalid trigger_kind: {wf.trigger_kind}")

    workflow = Workflow(
        name=wf.name,
        trigger=Trigger(kind=trigger_kind, config=wf.trigger_config),
        actions=[
            Action(
                tool=a["tool"],
                params=a.get("params", {}),
                on_fail=a.get("on_fail", "stop"),
            )
            for a in wf.actions
        ],
        description=wf.description,
        enabled=wf.enabled,
    )

    _automation_engine.add_workflow(workflow)

    # Start its schedule loop if it's a schedule trigger and engine is running
    if trigger_kind == TriggerKind.SCHEDULE and _automation_engine._running:
        import asyncio

        _automation_engine._schedule_tasks[wf.name] = asyncio.create_task(
            _automation_engine._schedule_loop(workflow),
            name=f"automation:{wf.name}",
        )

    return {"status": "created", "name": wf.name}


@router.delete("/workflows/{name}")
async def delete_workflow(name: str) -> dict[str, str]:
    """Delete an automation workflow."""
    if _automation_engine is None:
        raise HTTPException(503, "Automation engine not initialized")

    if _automation_engine.remove_workflow(name):
        return {"status": "deleted", "name": name}
    raise HTTPException(404, f"Workflow not found: {name}")


@router.get("/history")
async def workflow_history() -> list[dict[str, Any]]:
    """Return recent workflow execution history."""
    if _automation_engine is None:
        return []
    return [
        {
            "workflow": run.workflow_name,
            "success": run.success,
            "outputs": run.action_outputs[:5],  # Truncate
            "error": run.error,
            "elapsed_ms": round((run.finished_at - run.started_at) * 1000),
        }
        for run in _automation_engine.history[-20:]
    ]
