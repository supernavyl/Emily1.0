"""
Consent gate for Emily.

Before executing any action that modifies external state
(file writes, shell commands, Home Assistant calls, tool generation),
Emily must get explicit consent from the user.

Consent can be granted via:
1. Voice response ("yes", "confirm", "go ahead", etc.)
2. Terminal input (for headless / debug mode)
3. Desktop notification with yes/no action buttons (notify-send with urgency)

All consent decisions are recorded in the audit log.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from observability.logger import get_logger
from security.audit_log import AuditLog

log = get_logger(__name__)

# Words that count as spoken consent
_AFFIRMATIVE_WORDS = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "sure",
        "ok",
        "okay",
        "go",
        "proceed",
        "confirm",
        "affirm",
        "approved",
        "allow",
        "accept",
        "do it",
        "go ahead",
    }
)

# Words that count as spoken denial
_NEGATIVE_WORDS = frozenset(
    {
        "no",
        "nope",
        "nah",
        "stop",
        "cancel",
        "abort",
        "deny",
        "reject",
        "don't",
        "dont",
        "negative",
        "decline",
    }
)


class ConsentDecision(StrEnum):
    """Outcome of a consent request."""

    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"


@dataclass
class ConsentRequest:
    """A pending consent request."""

    action: str  # Human-readable action description
    tool_name: str  # Tool/plugin name
    actor: str  # Agent requesting consent
    parameters: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"  # "low" | "medium" | "high"


class ConsentGate:
    """
    Interactive consent gate for privileged actions.

    In voice mode, listens for an affirmative/negative response.
    Falls back to asyncio.Queue for programmatic consent during tests.
    """

    _DEFAULT_TIMEOUT_S = 30.0

    def __init__(
        self,
        audit_log: AuditLog,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        auto_approve_low_risk: bool = False,
    ) -> None:
        """
        Args:
            audit_log: AuditLog instance for recording decisions.
            timeout_s: Seconds to wait before treating silence as denial.
            auto_approve_low_risk: If True, automatically approve low-risk actions.
        """
        self._audit = audit_log
        self._timeout = timeout_s
        self._auto_approve_low_risk = auto_approve_low_risk
        self._pending_queue: asyncio.Queue[ConsentDecision] = asyncio.Queue(maxsize=1)

    async def request(self, req: ConsentRequest) -> ConsentDecision:
        """
        Ask the user for consent before executing a privileged action.

        Args:
            req: The ConsentRequest describing the action.

        Returns:
            ConsentDecision indicating the user's decision.
        """
        # Auto-approve low-risk actions when configured
        if self._auto_approve_low_risk and req.risk_level == "low":
            await self._audit.append(
                event="consent_auto_approved",
                actor=req.actor,
                payload={"tool": req.tool_name, "action": req.action, "risk": req.risk_level},
            )
            return ConsentDecision.APPROVED

        log.info(
            "consent_requested",
            tool=req.tool_name,
            action=req.action,
            risk=req.risk_level,
        )

        # Drain any stale pending decisions
        while not self._pending_queue.empty():
            try:
                self._pending_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Prompt via terminal (always available for debugging)
        decision = await self._terminal_prompt(req)

        await self._audit.append(
            event=f"consent_{decision.value}",
            actor=req.actor,
            payload={
                "tool": req.tool_name,
                "action": req.action,
                "risk": req.risk_level,
                "parameters": req.parameters,
            },
        )

        log.info("consent_decision", tool=req.tool_name, decision=decision.value)
        return decision

    async def _terminal_prompt(self, req: ConsentRequest) -> ConsentDecision:
        """
        Present a yes/no prompt in the terminal and wait for input.

        Args:
            req: The consent request.

        Returns:
            ConsentDecision based on terminal input.
        """
        prompt_text = (
            f"\n[EMILY CONSENT REQUEST]\n"
            f"  Tool: {req.tool_name}\n"
            f"  Action: {req.action}\n"
            f"  Risk: {req.risk_level.upper()}\n"
            f"  Requested by: {req.actor}\n"
            f"  Parameters: {req.parameters}\n"
            f"  Approve? [y/n] (timeout {int(self._timeout)}s): "
        )

        try:
            loop = asyncio.get_running_loop()
            answer = await asyncio.wait_for(
                loop.run_in_executor(None, input, prompt_text),
                timeout=self._timeout,
            )
            answer_lower = answer.strip().lower()
            if any(w in answer_lower for w in _AFFIRMATIVE_WORDS):
                return ConsentDecision.APPROVED
            return ConsentDecision.DENIED
        except TimeoutError:
            log.warning("consent_timeout", tool=req.tool_name, timeout_s=self._timeout)
            return ConsentDecision.TIMEOUT
        except EOFError:
            # Non-interactive (pipe/test) — default deny
            return ConsentDecision.DENIED

    def submit_voice_response(self, text: str) -> None:
        """
        Submit a voice-based consent response.

        Called by the ConversationAgent when the user speaks after a consent prompt.

        Args:
            text: Transcribed user speech.
        """
        text_lower = text.lower().strip()
        decision: ConsentDecision
        if any(w in text_lower for w in _AFFIRMATIVE_WORDS):
            decision = ConsentDecision.APPROVED
        elif any(w in text_lower for w in _NEGATIVE_WORDS):
            decision = ConsentDecision.DENIED
        else:
            return  # Ambiguous — ignore

        with contextlib.suppress(asyncio.QueueFull):
            self._pending_queue.put_nowait(decision)

    async def submit_programmatic(self, decision: ConsentDecision) -> None:
        """
        Programmatically submit a consent decision.

        Used in tests and automated workflows.

        Args:
            decision: The consent decision to submit.
        """
        await self._pending_queue.put(decision)
