"""Reasoning orchestrator — central intelligence for multi-strategy execution.

Implements five reasoning strategies selected by the active mode:

1. **Direct**           — single LLM call (current behaviour, zero overhead)
2. **Chain-of-Thought** — decompose → reason per sub-question → synthesize
3. **Tree-of-Thought**  — branch into N approaches, evaluate each, select best
4. **Consensus**        — run same prompt on N models, compare, synthesize
5. **Escalation**       — start at FAST, if confidence < threshold → SMART → REASONING → CLOUD

The orchestrator wraps but does NOT replace the existing ``chat_stream()`` path.
For the "direct" strategy it is a thin pass-through with zero overhead.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from observability.logger import get_logger

if TYPE_CHECKING:
    from llm.fleet import LLMFleet
    from llm.prompt_builder import PromptBuilder
    from modes.engine import OperationalMode

log = get_logger(__name__)


# ── Data classes ──────────────────────────────────────────────────


@dataclass
class ReasoningContext:
    """Everything the orchestrator needs to execute a strategy."""

    mode: OperationalMode
    skill_id: str = "normal"
    user_text: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    system_prompt: str = ""
    rag_context: str = ""
    conversation_history: list[dict] = field(default_factory=list)
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass
class ReasoningEvent:
    """Emitted to the SSE stream during reasoning execution."""

    event_type: str  # step_start | step_complete | thinking | model_switch | critique | branch | consensus | escalation
    step_name: str = ""
    model: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReasoningResult:
    """Final output of a reasoning execution."""

    text: str
    thinking: str = ""
    events: list[ReasoningEvent] = field(default_factory=list)
    models_used: list[str] = field(default_factory=list)
    total_tokens: int = 0
    total_latency_ms: float = 0
    strategy: str = "direct"
    confidence: float = 1.0


# Type alias for the event emitter callback
EventEmitter = Callable[[ReasoningEvent], Coroutine[Any, Any, None]]


class ReasoningOrchestrator:
    """Executes reasoning strategies using the LLM fleet."""

    # Confidence threshold for escalation strategy
    DEFAULT_ESCALATION_THRESHOLD = 0.6
    DEFAULT_TREE_BRANCHES = 3
    DEFAULT_MAX_CRITIC_LOOPS = 3

    # Tier escalation ladder
    _ESCALATION_LADDER = ["fast", "smart", "reasoning", "cloud_best"]

    def __init__(
        self,
        fleet: LLMFleet,
        prompts: PromptBuilder,
        *,
        escalation_threshold: float = 0.6,
        tree_branches: int = 3,
        max_critic_loops: int = 3,
    ) -> None:
        self._fleet = fleet
        self._prompts = prompts
        self._escalation_threshold = escalation_threshold
        self._tree_branches = tree_branches
        self._max_critic_loops = max_critic_loops

    async def execute(
        self,
        strategy: str,
        context: ReasoningContext,
        event_emitter: EventEmitter | None = None,
    ) -> ReasoningResult:
        """Run the specified reasoning strategy.

        Args:
            strategy: One of ``direct``, ``chain_of_thought``,
                ``tree_of_thought``, ``consensus``, ``escalation``.
            context: Full context including mode, messages, prompts.
            event_emitter: Async callback for SSE events (optional).

        Returns:
            :class:`ReasoningResult` with final text, events, and metrics.
        """
        emit = event_emitter or _noop_emitter
        dispatch = {
            "direct": self._execute_direct,
            "chain_of_thought": self._execute_cot,
            "tree_of_thought": self._execute_tot,
            "consensus": self._execute_consensus,
            "escalation": self._execute_escalation,
        }
        handler = dispatch.get(strategy, self._execute_direct)
        t0 = time.monotonic()
        result = await handler(context, emit)
        result.total_latency_ms = (time.monotonic() - t0) * 1000
        result.strategy = strategy
        return result

    # ── Strategy: Direct ──────────────────────────────────────────

    async def _execute_direct(
        self,
        ctx: ReasoningContext,
        emit: EventEmitter,
    ) -> ReasoningResult:
        """Single LLM call — pass-through to fleet.chat_stream()."""
        tier = ctx.mode.tier_preference[0] if ctx.mode.tier_preference else "smart"
        await emit(ReasoningEvent("step_start", "generate", tier))

        text, thinking, tokens = await self._call_fleet(
            ctx,
            force_tier=tier,
        )

        await emit(
            ReasoningEvent(
                "step_complete",
                "generate",
                tier,
                text[:200],
                {"tokens": tokens},
            )
        )

        return ReasoningResult(
            text=text,
            thinking=thinking,
            models_used=[tier],
            total_tokens=tokens,
        )

    # ── Strategy: Chain-of-Thought ────────────────────────────────

    async def _execute_cot(
        self,
        ctx: ReasoningContext,
        emit: EventEmitter,
    ) -> ReasoningResult:
        """Decompose → reason per sub-question → synthesize."""
        events: list[ReasoningEvent] = []
        models_used: list[str] = []
        total_tokens = 0

        # Step 1: Decompose the question
        await emit(ReasoningEvent("step_start", "decompose", "fast"))
        decompose_prompt = self._prompts.build_decompose_prompt(ctx.user_text)
        decompose_ctx = self._with_system(ctx, decompose_prompt)
        decomposition, _, tok = await self._call_fleet(decompose_ctx, force_tier="fast")
        total_tokens += tok
        models_used.append("fast")
        events.append(ReasoningEvent("step_complete", "decompose", "fast", decomposition[:200]))
        await emit(events[-1])

        # Step 2: Reason through each sub-question
        reason_tier = ctx.mode.tier_preference[0] if ctx.mode.tier_preference else "reasoning"
        await emit(ReasoningEvent("step_start", "reason", reason_tier))
        reason_prompt = self._prompts.build_reasoning_step_prompt(ctx.user_text, decomposition)
        reason_ctx = self._with_system(ctx, reason_prompt)
        reasoning, thinking, tok = await self._call_fleet(reason_ctx, force_tier=reason_tier)
        total_tokens += tok
        models_used.append(reason_tier)
        events.append(ReasoningEvent("step_complete", "reason", reason_tier, reasoning[:200]))
        await emit(events[-1])

        # Step 3: Synthesize
        await emit(ReasoningEvent("step_start", "synthesize", "smart"))
        synth_prompt = self._prompts.build_synthesize_prompt(ctx.user_text, reasoning)
        synth_ctx = self._with_system(ctx, synth_prompt)
        synthesis, _, tok = await self._call_fleet(synth_ctx, force_tier="smart")
        total_tokens += tok
        models_used.append("smart")
        events.append(ReasoningEvent("step_complete", "synthesize", "smart", synthesis[:200]))
        await emit(events[-1])

        return ReasoningResult(
            text=synthesis,
            thinking=thinking,
            events=events,
            models_used=models_used,
            total_tokens=total_tokens,
        )

    # ── Strategy: Tree-of-Thought ─────────────────────────────────

    async def _execute_tot(
        self,
        ctx: ReasoningContext,
        emit: EventEmitter,
    ) -> ReasoningResult:
        """Branch into N approaches, evaluate each, select best."""
        events: list[ReasoningEvent] = []
        models_used: list[str] = []
        total_tokens = 0
        n_branches = self._tree_branches

        # Step 1: Generate N distinct approaches in parallel
        tier = ctx.mode.tier_preference[0] if ctx.mode.tier_preference else "smart"
        branch_tasks = []
        for i in range(n_branches):
            branch_prompt = self._prompts.build_branch_prompt(ctx.user_text, i, n_branches)
            branch_ctx = self._with_system(ctx, branch_prompt)
            branch_tasks.append(self._call_fleet(branch_ctx, force_tier=tier))
            await emit(ReasoningEvent("branch", f"branch_{i}", tier, metadata={"branch_id": i}))

        branches = await asyncio.gather(*branch_tasks)
        branch_texts = []
        for i, (text, _thinking, tok) in enumerate(branches):
            total_tokens += tok
            branch_texts.append(text)
            models_used.append(tier)
            events.append(
                ReasoningEvent(
                    "step_complete",
                    f"branch_{i}",
                    tier,
                    text[:200],
                    {"branch_id": i, "tokens": tok},
                )
            )
            await emit(events[-1])

        # Step 2: Evaluate and select best
        eval_tier = "reasoning"
        await emit(ReasoningEvent("step_start", "evaluate", eval_tier))
        eval_prompt = self._prompts.build_evaluate_branches_prompt(
            ctx.user_text,
            branch_texts,
        )
        eval_ctx = self._with_system(ctx, eval_prompt)
        evaluation, _, tok = await self._call_fleet(eval_ctx, force_tier=eval_tier)
        total_tokens += tok
        models_used.append(eval_tier)
        events.append(ReasoningEvent("step_complete", "evaluate", eval_tier, evaluation[:200]))
        await emit(events[-1])

        # Step 3: Synthesize final answer from best branch + evaluation
        await emit(ReasoningEvent("step_start", "synthesize", "smart"))
        synth_prompt = self._prompts.build_synthesize_prompt(ctx.user_text, evaluation)
        synth_ctx = self._with_system(ctx, synth_prompt)
        synthesis, _, tok = await self._call_fleet(synth_ctx, force_tier="smart")
        total_tokens += tok
        models_used.append("smart")
        events.append(ReasoningEvent("step_complete", "synthesize", "smart", synthesis[:200]))
        await emit(events[-1])

        return ReasoningResult(
            text=synthesis,
            events=events,
            models_used=models_used,
            total_tokens=total_tokens,
        )

    # ── Strategy: Consensus ───────────────────────────────────────

    async def _execute_consensus(
        self,
        ctx: ReasoningContext,
        emit: EventEmitter,
    ) -> ReasoningResult:
        """Run same prompt on N models, compare outputs, synthesize."""
        events: list[ReasoningEvent] = []
        total_tokens = 0

        # Determine which tiers to use
        consensus_tiers = (
            ctx.mode.consensus_models if ctx.mode.consensus_models else ["smart", "reasoning"]
        )
        await emit(
            ReasoningEvent(
                "consensus",
                "start",
                "",
                metadata={"models": consensus_tiers},
            )
        )

        # Run all models in parallel
        tasks = []
        for tier in consensus_tiers:
            tasks.append(self._call_fleet(ctx, force_tier=tier))
            await emit(ReasoningEvent("step_start", f"model_{tier}", tier))

        results = await asyncio.gather(*tasks)
        model_outputs: list[str] = []
        for tier, (text, _thinking, tok) in zip(consensus_tiers, results, strict=False):
            total_tokens += tok
            model_outputs.append(text)
            events.append(
                ReasoningEvent(
                    "step_complete",
                    f"model_{tier}",
                    tier,
                    text[:300],
                    {"tokens": tok},
                )
            )
            await emit(events[-1])

        # Synthesize consensus
        await emit(ReasoningEvent("step_start", "consensus_synthesize", "smart"))
        synth_prompt = self._prompts.build_consensus_prompt(
            ctx.user_text,
            consensus_tiers,
            model_outputs,
        )
        synth_ctx = self._with_system(ctx, synth_prompt)
        synthesis, _, tok = await self._call_fleet(synth_ctx, force_tier="smart")
        total_tokens += tok
        events.append(
            ReasoningEvent(
                "consensus",
                "complete",
                "smart",
                synthesis[:200],
                {"models_compared": len(consensus_tiers)},
            )
        )
        await emit(events[-1])

        return ReasoningResult(
            text=synthesis,
            events=events,
            models_used=consensus_tiers + ["smart"],
            total_tokens=total_tokens,
        )

    # ── Strategy: Escalation ──────────────────────────────────────

    async def _execute_escalation(
        self,
        ctx: ReasoningContext,
        emit: EventEmitter,
    ) -> ReasoningResult:
        """Start at FAST, escalate if confidence is low."""
        events: list[ReasoningEvent] = []
        models_used: list[str] = []
        total_tokens = 0

        for tier in self._ESCALATION_LADDER:
            await emit(ReasoningEvent("step_start", f"attempt_{tier}", tier))
            text, thinking, tok = await self._call_fleet(ctx, force_tier=tier)
            total_tokens += tok
            models_used.append(tier)

            # Estimate confidence from the response
            confidence = self._estimate_confidence(text, thinking)
            events.append(
                ReasoningEvent(
                    "step_complete",
                    f"attempt_{tier}",
                    tier,
                    text[:200],
                    {"tokens": tok, "confidence": confidence},
                )
            )
            await emit(events[-1])

            if confidence >= self._escalation_threshold:
                log.info(
                    "escalation_resolved",
                    tier=tier,
                    confidence=confidence,
                )
                return ReasoningResult(
                    text=text,
                    thinking=thinking,
                    events=events,
                    models_used=models_used,
                    total_tokens=total_tokens,
                    confidence=confidence,
                )

            # Escalate
            await emit(
                ReasoningEvent(
                    "escalation",
                    f"escalate_from_{tier}",
                    tier,
                    f"Confidence {confidence:.2f} < {self._escalation_threshold}, escalating",
                )
            )

        # Exhausted all tiers — return last result
        return ReasoningResult(
            text=text,  # type: ignore[possibly-undefined]
            thinking=thinking,  # type: ignore[possibly-undefined]
            events=events,
            models_used=models_used,
            total_tokens=total_tokens,
            confidence=confidence,  # type: ignore[possibly-undefined]
        )

    # ── Helpers ───────────────────────────────────────────────────

    async def _call_fleet(
        self,
        ctx: ReasoningContext,
        *,
        force_tier: str = "smart",
    ) -> tuple[str, str, int]:
        """Call the LLM fleet and collect the full response.

        Returns:
            ``(response_text, thinking_text, token_count)``
        """
        from llm.router import ModelTier

        tier_enum = ModelTier(force_tier)
        chunks: list[str] = []
        token_count = 0

        async for chunk in self._fleet.chat_stream(
            user_message=ctx.user_text,
            messages=ctx.messages,
            force_tier=tier_enum,
            temperature=ctx.temperature or ctx.mode.temperature_override,
            max_tokens=ctx.max_tokens or ctx.mode.max_tokens_override,
        ):
            chunks.append(chunk)

        full_text = "".join(chunks)
        # Extract thinking if present
        thinking = ""
        if "<think>" in full_text:
            from llm.fleet import extract_thinking

            thinking, full_text = extract_thinking(full_text)

        # Rough token estimate
        token_count = len(full_text.split()) + len(thinking.split())

        return full_text, thinking, token_count

    def _with_system(self, ctx: ReasoningContext, system_prompt: str) -> ReasoningContext:
        """Clone context with a different system prompt injected into messages."""
        new_messages = list(ctx.messages)
        if new_messages and new_messages[0].get("role") == "system":
            new_messages[0] = {"role": "system", "content": system_prompt}
        else:
            new_messages.insert(0, {"role": "system", "content": system_prompt})
        return ReasoningContext(
            mode=ctx.mode,
            skill_id=ctx.skill_id,
            user_text=ctx.user_text,
            messages=new_messages,
            system_prompt=system_prompt,
            rag_context=ctx.rag_context,
            conversation_history=ctx.conversation_history,
            temperature=ctx.temperature,
            max_tokens=ctx.max_tokens,
        )

    @staticmethod
    def _estimate_confidence(text: str, thinking: str) -> float:
        """Heuristic confidence estimation from response characteristics."""
        combined = (thinking + " " + text).lower()

        # Start at neutral confidence
        score = 0.7

        # Uncertainty markers reduce confidence
        uncertainty_markers = [
            "i'm not sure",
            "i'm unsure",
            "i don't know",
            "uncertain",
            "might be",
            "could be",
            "possibly",
            "perhaps",
            "it depends",
            "hard to say",
            "difficult to determine",
            "unclear",
            "i need more information",
            "wait",
            "hmm",
            "let me reconsider",
        ]
        for marker in uncertainty_markers:
            if marker in combined:
                score -= 0.05

        # Strong assertion markers increase confidence
        confidence_markers = [
            "the answer is",
            "therefore",
            "in conclusion",
            "clearly",
            "definitely",
            "certainly",
            "this means",
            "the solution is",
        ]
        for marker in confidence_markers:
            if marker in combined:
                score += 0.03

        # Longer thinking generally means the model worked harder
        thinking_words = len(thinking.split())
        if thinking_words > 200:
            score += 0.05
        elif thinking_words < 20 and thinking:
            score -= 0.05

        # Very short responses for complex questions → low confidence
        if len(text.split()) < 20:
            score -= 0.1

        return max(0.0, min(1.0, score))


async def _noop_emitter(event: ReasoningEvent) -> None:
    """Default no-op event emitter."""
    pass
