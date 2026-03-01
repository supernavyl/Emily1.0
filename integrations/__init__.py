"""Emily integrations — CrewAI-style orchestration, automation, and external messaging."""

from integrations.automation import Action, AutomationEngine, Trigger, TriggerKind, Workflow
from integrations.crews import Crew, CrewAgent, CrewResult, CrewTask

__all__ = [
    "AutomationEngine",
    "Trigger",
    "TriggerKind",
    "Workflow",
    "Action",
    "Crew",
    "CrewAgent",
    "CrewTask",
    "CrewResult",
]
