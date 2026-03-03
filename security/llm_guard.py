"""
LLM Guard integration — input/output scanning for prompt injection,
toxicity, secrets leakage, and other safety concerns.

Wraps ``llm-guard`` scanners with a simple interface:
- ``scan_input(prompt)`` — checks user messages before LLM inference
- ``scan_output(prompt, response)`` — checks LLM responses before delivery

Falls back to no-op passthrough if ``llm-guard`` is not installed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class ScanResult:
    """Result of an LLM Guard scan."""

    text: str
    is_valid: bool
    scores: dict[str, float] = field(default_factory=dict)
    flagged_scanners: list[str] = field(default_factory=list)


class LLMGuard:
    """
    Input/output scanner using LLM Guard.

    Scans prompts for injection attacks, toxicity, and secrets before
    sending to the LLM. Scans responses for sensitive data and safety
    issues before delivering to the user.

    Falls back to passthrough if llm-guard is not installed.
    """

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._available = False
        self._input_scanners: list[Any] = []
        self._output_scanners: list[Any] = []
        if enabled:
            self._init_scanners()

    def _init_scanners(self) -> None:
        """Load LLM Guard input and output scanners."""
        try:
            from llm_guard.input_scanners import (  # type: ignore[import-untyped]
                BanTopics,
                PromptInjection,
                Secrets,
                TokenLimit,
                Toxicity,
            )
            from llm_guard.output_scanners import (  # type: ignore[import-untyped]
                BanTopics as OutputBanTopics,
            )
            from llm_guard.output_scanners import (
                NoRefusal,
                Sensitive,
            )
            from llm_guard.output_scanners import (
                Toxicity as OutputToxicity,
            )

            self._input_scanners = [
                PromptInjection(threshold=0.9),
                Toxicity(threshold=0.8),
                Secrets(),
                TokenLimit(limit=8192),
                BanTopics(topics=["violence", "self-harm"], threshold=0.8),
            ]
            self._output_scanners = [
                OutputToxicity(threshold=0.8),
                Sensitive(),
                NoRefusal(threshold=0.5),
                OutputBanTopics(topics=["violence", "self-harm"], threshold=0.8),
            ]
            self._available = True
            log.info(
                "llm_guard_loaded",
                input_scanners=len(self._input_scanners),
                output_scanners=len(self._output_scanners),
            )
        except ImportError:
            log.info("llm_guard_unavailable (llm-guard not installed — passthrough)")
        except Exception as exc:
            log.warning("llm_guard_init_failed: %s", exc)

    async def scan_input(self, prompt: str) -> ScanResult:
        """
        Scan a user prompt before sending to the LLM.

        Args:
            prompt: The user's input text.

        Returns:
            ScanResult with sanitized text and validation status.
        """
        if not self._available:
            return ScanResult(text=prompt, is_valid=True)

        return await asyncio.to_thread(self._scan_input_sync, prompt)

    def _scan_input_sync(self, prompt: str) -> ScanResult:
        """Blocking input scan."""
        from llm_guard import scan_prompt  # type: ignore[import-untyped]

        sanitized, results_valid, results_score = scan_prompt(self._input_scanners, prompt)

        flagged = [name for name, valid in results_valid.items() if not valid]

        if flagged:
            log.warning(
                "llm_guard_input_flagged",
                flagged=flagged,
                scores={k: round(v, 3) for k, v in results_score.items()},
            )

        return ScanResult(
            text=sanitized,
            is_valid=all(results_valid.values()),
            scores={k: round(v, 3) for k, v in results_score.items()},
            flagged_scanners=flagged,
        )

    async def scan_output(self, prompt: str, response: str) -> ScanResult:
        """
        Scan an LLM response before delivering to the user.

        Args:
            prompt: The original user prompt.
            response: The LLM's response text.

        Returns:
            ScanResult with sanitized response and validation status.
        """
        if not self._available:
            return ScanResult(text=response, is_valid=True)

        return await asyncio.to_thread(self._scan_output_sync, prompt, response)

    def _scan_output_sync(self, prompt: str, response: str) -> ScanResult:
        """Blocking output scan."""
        from llm_guard import scan_output  # type: ignore[import-untyped]

        sanitized, results_valid, results_score = scan_output(
            self._output_scanners, prompt, response
        )

        flagged = [name for name, valid in results_valid.items() if not valid]

        if flagged:
            log.warning(
                "llm_guard_output_flagged",
                flagged=flagged,
                scores={k: round(v, 3) for k, v in results_score.items()},
            )

        return ScanResult(
            text=sanitized,
            is_valid=all(results_valid.values()),
            scores={k: round(v, 3) for k, v in results_score.items()},
            flagged_scanners=flagged,
        )

    @property
    def available(self) -> bool:
        """True if LLM Guard scanners are loaded."""
        return self._available
