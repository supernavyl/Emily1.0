"""Skill pipeline executor — runs multi-step skill pipelines.

Given a :class:`EmilySkill` with a non-empty ``pipeline``, the executor runs
each :class:`PipelineStep` in order, threading context from earlier steps
into later ones via ``pass_context_from``.

For skills without a pipeline (``has_pipeline is False``), callers should
fall through to the standard single-shot :class:`ReasoningOrchestrator`.

Progress events are emitted per step so the frontend can show real-time
pipeline visualisation.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from observability.logger import get_logger

if TYPE_CHECKING:
    from emily_chat.emily.skills import EmilySkill, PipelineStep
    from llm.fleet import LLMFleet
    from llm.prompt_builder import PromptBuilder

log = get_logger(__name__)


@dataclass
class StepResult:
    """Output of a single pipeline step."""

    step_name: str
    tier: str
    text: str
    thinking: str = ""
    tokens: int = 0
    latency_ms: float = 0


@dataclass
class PipelineResult:
    """Aggregated output from a full pipeline execution."""

    final_text: str
    steps: list[StepResult] = field(default_factory=list)
    total_tokens: int = 0
    total_latency_ms: float = 0


@dataclass
class SkillProgressEvent:
    """Emitted to SSE during pipeline execution."""

    event_type: str = "skill_progress"
    skill_id: str = ""
    step_name: str = ""
    step_index: int = 0
    total_steps: int = 0
    status: str = ""  # "started" | "completed" | "failed"
    tier: str = ""
    content_preview: str = ""
    tokens: int = 0
    latency_ms: float = 0


ProgressEmitter = Callable[[SkillProgressEvent], Coroutine[Any, Any, None]]


class SkillPipelineExecutor:
    """Executes multi-step skill pipelines using the LLM fleet."""

    def __init__(
        self,
        fleet: LLMFleet,
        prompts: PromptBuilder,
    ) -> None:
        self._fleet = fleet
        self._prompts = prompts

    async def execute(
        self,
        skill: EmilySkill,
        skill_id: str,
        user_text: str,
        messages: list[dict[str, str]],
        *,
        event_emitter: ProgressEmitter | None = None,
    ) -> PipelineResult:
        """Run a skill's pipeline steps sequentially.

        Args:
            skill: The skill containing the pipeline definition.
            skill_id: Skill identifier for event tagging.
            user_text: The user's original query.
            messages: Conversation messages for context.
            event_emitter: Async callback for progress events.

        Returns:
            :class:`PipelineResult` with the final step's output.
        """
        emit = event_emitter or _noop_progress
        steps = skill.pipeline
        total_steps = len(steps)
        step_outputs: dict[str, str] = {}
        results: list[StepResult] = []
        total_tokens = 0
        t0 = time.monotonic()

        for i, step in enumerate(steps):
            await emit(
                SkillProgressEvent(
                    skill_id=skill_id,
                    step_name=step.name,
                    step_index=i,
                    total_steps=total_steps,
                    status="started",
                    tier=step.tier,
                )
            )

            step_t0 = time.monotonic()

            # Build context from prior step output if specified
            prior_context = ""
            if step.pass_context_from and step.pass_context_from in step_outputs:
                prior_context = step_outputs[step.pass_context_from]

            # Build the system prompt for this step
            system_prompt = self._build_step_prompt(
                step,
                user_text,
                prior_context,
                skill,
            )

            # Execute the LLM call
            text, thinking, tokens = await self._call_fleet(
                system_prompt=system_prompt,
                user_text=user_text,
                prior_context=prior_context,
                messages=messages,
                tier=step.tier,
                max_tokens=step.max_tokens,
            )

            step_latency = (time.monotonic() - step_t0) * 1000
            total_tokens += tokens

            step_result = StepResult(
                step_name=step.name,
                tier=step.tier,
                text=text,
                thinking=thinking,
                tokens=tokens,
                latency_ms=step_latency,
            )
            results.append(step_result)
            step_outputs[step.name] = text

            await emit(
                SkillProgressEvent(
                    skill_id=skill_id,
                    step_name=step.name,
                    step_index=i,
                    total_steps=total_steps,
                    status="completed",
                    tier=step.tier,
                    content_preview=text[:200],
                    tokens=tokens,
                    latency_ms=step_latency,
                )
            )

            log.debug(
                "pipeline_step_complete",
                skill=skill_id,
                step=step.name,
                tier=step.tier,
                tokens=tokens,
                latency_ms=round(step_latency, 1),
            )

        total_latency = (time.monotonic() - t0) * 1000

        return PipelineResult(
            final_text=results[-1].text if results else "",
            steps=results,
            total_tokens=total_tokens,
            total_latency_ms=total_latency,
        )

    def _build_step_prompt(
        self,
        step: PipelineStep,
        user_text: str,
        prior_context: str,
        skill: EmilySkill,
    ) -> str:
        """Build a system prompt for a pipeline step using the prompt builder."""
        # Try to use a specific prompt builder method based on prompt_key
        key = step.prompt_key
        builder_methods = {
            "decompose": lambda: self._prompts.build_decompose_prompt(user_text),
            "reasoning": lambda: self._prompts.build_reasoning_step_prompt(
                user_text, prior_context
            ),
            "synthesize": lambda: self._prompts.build_synthesize_prompt(user_text, prior_context),
            "critique": lambda: self._prompts.build_critique_loop_prompt(prior_context, user_text),
            "code_implement": lambda: self._prompts.build_code_implement_prompt(
                user_text, prior_context
            ),
            "web_search": lambda: self._prompts.build_web_search_prompt(user_text, prior_context),
            "debate_position": lambda: self._prompts.build_debate_position_prompt(user_text),
            "debate_counter": lambda: self._prompts.build_debate_counter_prompt(
                user_text, prior_context
            ),
        }

        builder = builder_methods.get(key)
        if builder:
            return builder()

        # Fallback: use the skill's system_addition with context
        parts = []
        if skill.system_addition:
            parts.append(skill.system_addition)
        if prior_context:
            parts.append(f"\n\nPrior analysis:\n{prior_context}")
        return "\n".join(parts) if parts else f"Complete this step: {step.name}"

    async def _call_fleet(
        self,
        *,
        system_prompt: str,
        user_text: str,
        prior_context: str,
        messages: list[dict[str, str]],
        tier: str,
        max_tokens: int,
    ) -> tuple[str, str, int]:
        """Execute a single LLM call for a pipeline step."""
        from llm.router import ModelTier

        tier_enum = ModelTier(tier)

        # Build messages with step-specific system prompt
        step_messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
        ]
        # Include recent conversation context (last 4 messages)
        for msg in messages[-4:]:
            if msg.get("role") != "system":
                step_messages.append(msg)

        # Add the user query with prior context if available
        user_content = user_text
        if prior_context:
            user_content = f"{user_text}\n\n<prior_analysis>\n{prior_context}\n</prior_analysis>"
        step_messages.append({"role": "user", "content": user_content})

        chunks: list[str] = []
        async for chunk in self._fleet.chat_stream(
            user_message=user_text,
            messages=step_messages,
            force_tier=tier_enum,
            max_tokens=max_tokens,
        ):
            chunks.append(chunk)

        full_text = "".join(chunks)
        thinking = ""
        if "<think>" in full_text:
            from llm.fleet import extract_thinking

            thinking, full_text = extract_thinking(full_text)

        token_count = len(full_text.split()) + len(thinking.split())
        return full_text, thinking, token_count


async def _noop_progress(event: SkillProgressEvent) -> None:
    """Default no-op progress emitter."""
    pass
