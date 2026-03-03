"""
Security manager — unified access point for all security subsystems.

Provides:
- PII scrubbing for log entries and memory writes
- Consent gate for privileged tool execution
- Tamper-evident audit logging
- Dead man's switch background monitor
- Encryption at rest helpers
"""

from __future__ import annotations

from pathlib import Path

from config import SecurityConfig
from observability.logger import get_logger
from security.audit_log import AuditLog
from security.consent import ConsentDecision, ConsentGate, ConsentRequest
from security.dead_man_switch import DeadManSwitch
from security.encryption import AgeEncryption
from security.llm_guard import LLMGuard
from security.llm_guard import ScanResult as LLMGuardResult
from security.pii_scrubber import PIIScrubber, ScrubResult

log = get_logger(__name__)


class SecurityManager:
    """
    Root security object. Composes all security subsystems.

    Intended usage:
        security = SecurityManager(config)
        await security.start()
        ...
        await security.stop()
    """

    def __init__(self, config: SecurityConfig) -> None:
        """
        Args:
            config: Security configuration block.
        """
        self._config = config
        self.audit_log = AuditLog(path=config.audit_log_path)
        self.pii_scrubber = PIIScrubber() if config.pii_scrub else _NoOpScrubber()
        self.consent_gate = ConsentGate(
            audit_log=self.audit_log,
            auto_approve_low_risk=False,
        )
        self.dead_man_switch = DeadManSwitch(
            audit_log=self.audit_log,
            threshold_days=config.dead_man_switch_days,
            heartbeat_path=config.dead_man_switch_heartbeat_path,
        )
        self.encryption = AgeEncryption(
            key_path=Path(config.key_file).expanduser(),
            strict=config.encrypt_at_rest,
        )
        self.llm_guard = LLMGuard(enabled=True)

    async def start(self) -> None:
        """Start background security services."""
        if self._config.encrypt_at_rest:
            try:
                self.encryption.ensure_key()
            except Exception as exc:
                log.error("encryption_key_init_failed", error=str(exc))
                raise RuntimeError(
                    "Encryption at rest is enabled but key setup failed. "
                    "Fix the error above or set security.encrypt_at_rest to false."
                ) from exc

        if self._config.audit_retention_days > 0:
            try:
                removed = await self.audit_log.trim_retention_days(
                    self._config.audit_retention_days
                )
                if removed > 0:
                    log.info("audit_retention_trimmed_on_start", removed=removed)
            except Exception as exc:
                log.warning("audit_retention_trim_failed", error=str(exc))

        await self.dead_man_switch.start()
        await self.audit_log.append(
            event="emily_started",
            actor="SecurityManager",
            payload={"version": "1.0"},
        )
        log.info("security_manager_started")

    async def stop(self) -> None:
        """Stop background security services."""
        await self.dead_man_switch.stop()
        await self.audit_log.append(
            event="emily_stopped",
            actor="SecurityManager",
            payload={},
        )
        log.info("security_manager_stopped")

    def scrub(self, text: str) -> str:
        """Scrub PII from a text string. Returns cleaned text."""
        return self.pii_scrubber.scrub(text).scrubbed

    async def require_consent(
        self,
        tool_name: str,
        action: str,
        actor: str,
        parameters: dict | None = None,
        risk_level: str = "medium",
    ) -> bool:
        """
        Request user consent for a privileged action.

        Args:
            tool_name: Name of the tool requiring consent.
            action: Human-readable description of the action.
            actor: Agent requesting the action.
            parameters: Action parameters for display.
            risk_level: "low" | "medium" | "high".

        Returns:
            True if the user approved, False otherwise.
        """
        # Tools not in the approval list skip the gate
        if tool_name not in self._config.require_approval_tools:
            return True

        req = ConsentRequest(
            action=action,
            tool_name=tool_name,
            actor=actor,
            parameters=parameters or {},
            risk_level=risk_level,
        )
        decision = await self.consent_gate.request(req)
        return decision == ConsentDecision.APPROVED

    async def scan_input(self, prompt: str) -> LLMGuardResult:
        """Scan user input for prompt injection, toxicity, and secrets."""
        return await self.llm_guard.scan_input(prompt)

    async def scan_output(self, prompt: str, response: str) -> LLMGuardResult:
        """Scan LLM output for safety issues before delivery."""
        return await self.llm_guard.scan_output(prompt, response)

    def record_heartbeat(self) -> None:
        """Record a user interaction heartbeat for the dead man's switch."""
        self.dead_man_switch.heartbeat()


class _NoOpScrubber:
    """A no-op scrubber used when PII scrubbing is disabled."""

    def scrub(self, text: str) -> ScrubResult:
        from security.pii_scrubber import ScrubResult

        return ScrubResult(original=text, scrubbed=text, entities_found=[])

    def scrub_dict(self, data: dict, fields: list | None = None) -> dict:
        return data

    def is_ner_available(self) -> bool:
        return False
