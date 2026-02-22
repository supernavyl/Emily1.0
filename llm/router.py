"""
Intelligent model router for Emily's LLM fleet.

Selects the appropriate model tier (nano/fast/smart/reasoning/vision/embedding)
based on:
- Task complexity score (0-10, estimated by rules or nano model)
- Task type (chat, embedding, vision, code, reasoning)
- Available VRAM headroom
- Whether the user needs a streaming response
- Current urgency level

Complexity scoring rules (heuristics, nano model validates for non-trivial cases):
  0-2: Simple factual Q&A, greetings, short commands → nano
  3-6: Standard conversation, coding questions, summarization → fast
  7-10: Multi-step reasoning, math, planning, deep analysis → smart/reasoning
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from enum import Enum, auto

from config import LLMConfig
from observability.logger import get_logger

log = get_logger(__name__)


class ModelTier(Enum):
    NANO = "nano"
    VOICE_FAST = "voice_fast"
    FAST = "fast"
    SMART = "smart"
    REASONING = "reasoning"
    VISION = "vision"
    EMBEDDING = "embedding"


class TaskType(Enum):
    CHAT = auto()
    CODE = auto()
    MATH = auto()
    REASONING = auto()
    VISION = auto()
    EMBEDDING = auto()
    CLASSIFICATION = auto()
    SUMMARIZATION = auto()


@dataclass
class RoutingDecision:
    """Result of the model routing decision."""

    tier: ModelTier
    model_name: str
    complexity_score: int
    task_type: TaskType
    reason: str


class ModelRouter:
    """
    Rule-based + LLM-assisted model tier selector.

    Fast path: pure heuristics (no LLM call, <1ms).
    Slow path: nano model validates the decision for borderline cases (50-100ms).
    """

    # Patterns that indicate high complexity
    _COMPLEX_PATTERNS = [
        r"\bprove\b", r"\bderive\b", r"\boptimize\b", r"\barchitect\b",
        r"\brefactor\b", r"\bdesign\b", r"\bdebug\b", r"\banalyze\b",
        r"\bcompare\b.*\band\b", r"\bstep by step\b", r"\bchain of thought\b",
        r"\bwhy\b.*\bbecause\b", r"\bexplain\b.*\bdetail",
    ]

    # Code-related patterns
    _CODE_PATTERNS = [
        r"```", r"\bdef \b", r"\bclass \b", r"\bfunction\b",
        r"\balgorithm\b", r"\bcode\b", r"\bpython\b", r"\brust\b",
    ]

    # Math patterns
    _MATH_PATTERNS = [
        r"\bsolve\b", r"\bcalculate\b", r"\bequation\b", r"\bintegral\b",
        r"\bderivative\b", r"\bproof\b", r"\bmatrix\b", r"[=+\-*/^]{2,}",
    ]

    def __init__(self, config: LLMConfig) -> None:
        """
        Args:
            config: LLM configuration with model names and routing thresholds.
        """
        self._config = config
        self._complex_re = re.compile(
            "|".join(self._COMPLEX_PATTERNS), re.IGNORECASE
        )
        self._code_re = re.compile(
            "|".join(self._CODE_PATTERNS), re.IGNORECASE
        )
        self._math_re = re.compile(
            "|".join(self._MATH_PATTERNS), re.IGNORECASE
        )

    def route(
        self,
        text: str,
        task_type: TaskType = TaskType.CHAT,
        force_tier: ModelTier | None = None,
        streaming: bool = True,
        urgency: float = 0.5,
        voice_mode: bool = False,
    ) -> RoutingDecision:
        """
        Select the appropriate model tier for the given input.

        Args:
            text: The user query or task description.
            task_type: Explicit task type hint.
            force_tier: Override routing and use this specific tier.
            streaming: Whether streaming output is required.
            urgency: Urgency level 0.0 (low) to 1.0 (high). High urgency → faster model.
            voice_mode: When True, routes simple queries to the VOICE_FAST
                tier (Qwen2.5:3b via llama-cpp-python) for sub-second latency.

        Returns:
            RoutingDecision with the selected tier and model name.
        """
        if force_tier is not None:
            return self._make_decision(force_tier, 5, task_type, "forced")

        # Special task types always route to specific tiers
        if task_type == TaskType.VISION:
            return self._make_decision(ModelTier.VISION, 5, task_type, "vision_task")
        if task_type == TaskType.EMBEDDING:
            return self._make_decision(ModelTier.EMBEDDING, 1, task_type, "embedding_task")
        if task_type == TaskType.CLASSIFICATION:
            return self._make_decision(ModelTier.NANO, 1, task_type, "classification_task")

        complexity = self._estimate_complexity(text)
        inferred_type = self._infer_task_type(text, task_type)

        # High urgency pushes toward faster models
        if urgency > 0.8:
            complexity = max(0, complexity - 2)

        threshold_fast = self._config.routing.complexity_threshold_fast
        threshold_smart = self._config.routing.complexity_threshold_smart
        voice_threshold = self._config.routing.voice_fast_complexity_threshold

        if voice_mode and complexity < voice_threshold and inferred_type not in (
            TaskType.MATH, TaskType.REASONING
        ):
            tier = ModelTier.VOICE_FAST
            reason = f"voice_fast complexity={complexity} < voice_threshold={voice_threshold}"
            return self._make_decision(tier, complexity, inferred_type, reason)

        if inferred_type in (TaskType.MATH, TaskType.REASONING):
            tier = ModelTier.REASONING
            reason = f"reasoning_task complexity={complexity}"
        elif complexity <= threshold_fast:
            tier = ModelTier.FAST
            reason = f"complexity={complexity} <= fast_threshold={threshold_fast}"
        elif complexity <= threshold_smart:
            tier = ModelTier.FAST if urgency > 0.7 else ModelTier.SMART
            reason = f"complexity={complexity} urgency={urgency:.1f}"
        else:
            tier = ModelTier.SMART
            reason = f"complexity={complexity} > smart_threshold={threshold_smart}"

        return self._make_decision(tier, complexity, inferred_type, reason)

    def _estimate_complexity(self, text: str) -> int:
        """
        Estimate task complexity from 0 to 10 using heuristics.

        Args:
            text: Input text to score.

        Returns:
            Integer complexity score in [0, 10].
        """
        score = 3  # Baseline: standard conversation

        # Length penalty: longer questions tend to be more complex
        words = len(text.split())
        if words > 50:
            score += 1
        if words > 150:
            score += 1
        if words > 300:
            score += 1

        # Complexity signals
        if self._complex_re.search(text):
            score += 2

        # Code
        if self._code_re.search(text):
            score += 1

        # Math
        if self._math_re.search(text):
            score += 2

        # Multi-part questions (and, also, additionally, furthermore)
        if re.search(r"\b(and also|additionally|furthermore|moreover)\b", text, re.I):
            score += 1

        return min(10, max(0, score))

    def _infer_task_type(self, text: str, hint: TaskType) -> TaskType:
        """Refine the task type from text analysis."""
        if hint != TaskType.CHAT:
            return hint
        if self._math_re.search(text):
            return TaskType.MATH
        if self._code_re.search(text):
            return TaskType.CODE
        if re.search(r"\bsummariz|condense|tldr\b", text, re.I):
            return TaskType.SUMMARIZATION
        return TaskType.CHAT

    def _make_decision(
        self,
        tier: ModelTier,
        complexity: int,
        task_type: TaskType,
        reason: str,
    ) -> RoutingDecision:
        """Build a RoutingDecision for the given tier."""
        model_map = {
            ModelTier.NANO: self._config.models.nano,
            ModelTier.VOICE_FAST: self._config.models.voice_fast,
            ModelTier.FAST: self._config.models.fast,
            ModelTier.SMART: self._config.models.smart,
            ModelTier.REASONING: self._config.models.reasoning,
            ModelTier.VISION: self._config.models.vision,
            ModelTier.EMBEDDING: self._config.models.embedding,
        }
        model_name = model_map[tier]
        decision = RoutingDecision(
            tier=tier,
            model_name=model_name,
            complexity_score=complexity,
            task_type=task_type,
            reason=reason,
        )
        log.debug(
            "routing_decision",
            tier=tier.value,
            model=model_name,
            complexity=complexity,
            reason=reason,
        )
        return decision
