"""
CriticAgent self-evaluation loop for Emily.

After every non-trivial response, the CriticAgent scores the output on
four dimensions (accuracy, completeness, safety, helpfulness). If the
overall score falls below the configured threshold, Emily silently retries
with a revised approach, up to max_retries times.

This implements the CRITIQUE → REVISE portion of the ReAct++ loop.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from llm.client import ChatMessage
from llm.fleet import LLMFleet
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier
from llm.structured_output import extract_json
from observability.logger import get_logger
from observability.metrics import CRITIC_RETRIES_TOTAL

log = get_logger(__name__)


@dataclass
class CriticScore:
    """Structured evaluation output from the CriticAgent."""

    accuracy: float
    completeness: float
    safety: float
    helpfulness: float
    overall: float
    issues: list[str]
    suggestions: list[str]

    @property
    def passes_threshold(self) -> bool:
        """True if the overall score meets the minimum quality threshold."""
        return self.overall >= _MIN_CONFIDENCE

    @classmethod
    def default_pass(cls) -> "CriticScore":
        """Return a default passing score (used when critic is disabled)."""
        return cls(
            accuracy=1.0, completeness=1.0, safety=1.0, helpfulness=1.0,
            overall=1.0, issues=[], suggestions=[]
        )

    @classmethod
    def from_dict(cls, data: dict) -> "CriticScore":
        """Parse a CriticScore from a dict."""
        return cls(
            accuracy=float(data.get("accuracy", 0.7)),
            completeness=float(data.get("completeness", 0.7)),
            safety=float(data.get("safety", 1.0)),
            helpfulness=float(data.get("helpfulness", 0.7)),
            overall=float(data.get("overall", 0.7)),
            issues=data.get("issues", []),
            suggestions=data.get("suggestions", []),
        )


_MIN_CONFIDENCE = 0.65


class CriticLoop:
    """
    Self-evaluation and retry loop.

    Scores a response, and if it fails the quality threshold, generates
    a revised response. Max retries is bounded to prevent infinite loops.
    """

    def __init__(
        self,
        fleet: LLMFleet,
        prompt_builder: PromptBuilder,
        min_confidence: float = _MIN_CONFIDENCE,
        max_retries: int = 2,
        enabled: bool = True,
    ) -> None:
        """
        Args:
            fleet: LLM fleet for inference.
            prompt_builder: Prompt assembly.
            min_confidence: Minimum overall score to accept a response.
            max_retries: Maximum retry attempts before accepting the best response.
            enabled: If False, all responses pass immediately (disabled mode).
        """
        self._fleet = fleet
        self._prompts = prompt_builder
        self._min_confidence = min_confidence
        self._max_retries = max_retries
        self._enabled = enabled

    async def evaluate(
        self,
        response: str,
        task: str,
    ) -> CriticScore:
        """
        Score a response using the nano model as a fast critic.

        Args:
            response: The response text to evaluate.
            task: The original task or question.

        Returns:
            CriticScore with dimension scores and feedback.
        """
        if not self._enabled:
            return CriticScore.default_pass()

        critic_prompt = self._prompts.build_critic_prompt(response, task)
        result = await self._fleet.chat(
            user_message=critic_prompt,
            messages=[ChatMessage(role="user", content=critic_prompt)],
            force_tier=ModelTier.NANO,
            temperature=0.1,
        )

        parsed = extract_json(result.content)
        if parsed is None:
            log.warning("critic_parse_failed", response_preview=result.content[:80])
            return CriticScore.default_pass()

        return CriticScore.from_dict(parsed)

    async def evaluate_and_retry(
        self,
        initial_response: str,
        task: str,
        messages: list[ChatMessage],
    ) -> tuple[str, CriticScore]:
        """
        Evaluate a response and retry if below threshold.

        Args:
            initial_response: The initial LLM response to evaluate.
            task: The original task.
            messages: The conversation messages used to generate the initial response.

        Returns:
            Tuple of (best_response, final_score).
        """
        score = await self.evaluate(initial_response, task)
        log.debug(
            "critic_score",
            overall=f"{score.overall:.2f}",
            passes=score.passes_threshold,
        )

        if score.passes_threshold:
            return initial_response, score

        best_response = initial_response
        best_score = score

        for attempt in range(self._max_retries):
            CRITIC_RETRIES_TOTAL.inc()
            log.info(
                "critic_retry",
                attempt=attempt + 1,
                max=self._max_retries,
                score=f"{score.overall:.2f}",
                issues=score.issues,
            )

            # Build a retry prompt that includes the critic's feedback
            retry_guidance = (
                f"Your previous response was scored {score.overall:.2f}/1.0 "
                f"with these issues: {', '.join(score.issues)}. "
                f"Suggestions: {', '.join(score.suggestions)}. "
                "Please provide an improved response."
            )
            retry_messages = list(messages) + [
                ChatMessage(role="assistant", content=initial_response),
                ChatMessage(role="user", content=retry_guidance),
            ]

            retry_result = await self._fleet.chat(
                user_message=task,
                messages=retry_messages,
                temperature=0.5,
            )
            retry_response = retry_result.content

            new_score = await self.evaluate(retry_response, task)
            log.debug(
                "critic_retry_score",
                attempt=attempt + 1,
                overall=f"{new_score.overall:.2f}",
            )

            if new_score.overall > best_score.overall:
                best_response = retry_response
                best_score = new_score

            if best_score.passes_threshold:
                break

        if not best_score.passes_threshold:
            log.warning(
                "critic_all_retries_exhausted",
                best_score=f"{best_score.overall:.2f}",
                threshold=self._min_confidence,
            )

        return best_response, best_score
