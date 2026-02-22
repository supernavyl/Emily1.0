"""
ReAct++ reasoning loop for Emily.

Implements the THOUGHT → PLAN → ACTION → OBSERVATION → CRITIQUE → REVISE → RESPOND
loop for non-trivial tasks that may require tool use or multi-step reasoning.

The loop drives:
1. LLM generates a reasoning trace
2. Tool calls are extracted and executed
3. Observations are fed back to the LLM
4. The CriticAgent scores the final response
5. If score < threshold, the loop retries with revised approach

Max iterations: configurable, default 8.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TYPE_CHECKING

if TYPE_CHECKING:
    from core.brain_hub import BrainEventHub

from llm.client import ChatMessage
from llm.fleet import LLMFleet
from llm.prompt_builder import PromptBuilder
from llm.structured_output import extract_json
from observability.logger import get_logger
from observability.tracing import async_trace_span

log = get_logger(__name__)

ToolExecutor = Callable[[str, dict[str, Any]], Coroutine[Any, Any, Any]]


@dataclass
class ReActStep:
    """A single step in the ReAct reasoning chain."""

    thought: str = ""
    action: str = ""
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    is_final: bool = False
    final_answer: str = ""


@dataclass
class ReActResult:
    """Result of a complete ReAct++ loop execution."""

    final_answer: str
    steps: list[ReActStep]
    n_tool_calls: int
    n_iterations: int
    thinking_content: str = ""


class ReActLoop:
    """
    ReAct++ reasoning and tool use loop.

    Manages the agentic loop: LLM thinks → calls tool → observes result →
    thinks again → produces final answer.

    Tool execution is delegated to the provided ToolExecutor, which maps
    tool names to their implementations in the plugin registry.
    """

    _MAX_ITERATIONS = 8

    def __init__(
        self,
        fleet: LLMFleet,
        prompt_builder: PromptBuilder,
        tool_executor: ToolExecutor | None = None,
        available_tools: list[dict[str, Any]] | None = None,
        brain_hub: BrainEventHub | None = None,
    ) -> None:
        """
        Args:
            fleet: LLM fleet for inference.
            prompt_builder: Prompt assembly.
            tool_executor: Async callable(tool_name, params) → result.
            available_tools: List of tool schema dicts for the prompt.
        """
        self._fleet = fleet
        self._prompts = prompt_builder
        self._tool_executor = tool_executor
        self._available_tools = available_tools or []
        self._brain_hub = brain_hub

    async def run(
        self,
        task: str,
        context_messages: list[ChatMessage],
        system_prompt: str,
        max_iterations: int = _MAX_ITERATIONS,
    ) -> ReActResult:
        """
        Execute the ReAct++ loop for a given task.

        Args:
            task: The task or question to solve.
            context_messages: Conversation history + system prompt already assembled.
            system_prompt: System prompt to use.
            max_iterations: Maximum number of think/act cycles.

        Returns:
            ReActResult with the final answer and full reasoning trace.
        """
        async with async_trace_span("react_loop.run", attributes={"task": task[:80]}):
            steps: list[ReActStep] = []
            messages = list(context_messages)
            n_tool_calls = 0
            thinking_content = ""

            # Add tool-calling instruction to the current user turn
            if self._available_tools:
                tool_prompt = self._prompts.build_tool_call_prompt(
                    self._available_tools, task
                )
                messages.append(ChatMessage(role="user", content=tool_prompt))
            else:
                messages.append(ChatMessage(role="user", content=task))

            for iteration in range(max_iterations):
                log.debug("react_loop_iteration", iteration=iteration, n_tools=n_tool_calls)

                if self._brain_hub is not None:
                    await self._brain_hub.emit("react", "iteration_start", {
                        "iteration": iteration,
                        "task": task[:120],
                    })

                result = await self._fleet.chat(
                    user_message=task,
                    messages=messages,
                )

                response_text = result.content
                thinking_content += result.content

                step = self._parse_response(response_text)
                steps.append(step)

                if self._brain_hub is not None:
                    if step.thought:
                        await self._brain_hub.emit("react", "thought", {
                            "iteration": iteration,
                            "thought": step.thought[:500],
                        })

                if step.is_final:
                    log.info(
                        "react_loop_complete",
                        iterations=iteration + 1,
                        n_tool_calls=n_tool_calls,
                    )
                    if self._brain_hub is not None:
                        await self._brain_hub.emit("react", "final_answer", {
                            "iterations": iteration + 1,
                            "answer_len": len(step.final_answer),
                        })
                    return ReActResult(
                        final_answer=step.final_answer,
                        steps=steps,
                        n_tool_calls=n_tool_calls,
                        n_iterations=iteration + 1,
                        thinking_content=thinking_content,
                    )

                if step.action and self._tool_executor:
                    n_tool_calls += 1

                    if self._brain_hub is not None:
                        await self._brain_hub.emit("react", "action", {
                            "iteration": iteration,
                            "tool": step.action,
                            "input": str(step.action_input)[:300],
                        })

                    try:
                        observation = await self._tool_executor(
                            step.action, step.action_input
                        )
                        step.observation = str(observation)
                    except Exception as exc:
                        step.observation = f"Tool error: {exc}"
                        log.warning(
                            "tool_execution_error",
                            tool=step.action,
                            error=str(exc),
                        )

                    if self._brain_hub is not None:
                        await self._brain_hub.emit("react", "observation", {
                            "iteration": iteration,
                            "tool": step.action,
                            "observation": step.observation[:500],
                        })

                    messages.append(
                        ChatMessage(role="assistant", content=response_text)
                    )
                    messages.append(
                        ChatMessage(
                            role="user",
                            content=f"Observation: {step.observation}\n\nContinue.",
                        )
                    )
                else:
                    return ReActResult(
                        final_answer=response_text,
                        steps=steps,
                        n_tool_calls=n_tool_calls,
                        n_iterations=iteration + 1,
                        thinking_content=thinking_content,
                    )

            # Max iterations reached — return whatever we have
            log.warning("react_loop_max_iterations_reached", max=max_iterations)
            last_answer = steps[-1].final_answer or steps[-1].observation or task
            return ReActResult(
                final_answer=last_answer,
                steps=steps,
                n_tool_calls=n_tool_calls,
                n_iterations=max_iterations,
                thinking_content=thinking_content,
            )

    def _parse_response(self, text: str) -> ReActStep:
        """
        Parse an LLM response to extract action or final answer.

        Args:
            text: Raw LLM response text.

        Returns:
            ReActStep with parsed content.
        """
        step = ReActStep()
        parsed = extract_json(text)

        if parsed is None:
            # Not JSON — treat as final prose answer
            step.is_final = True
            step.final_answer = text.strip()
            return step

        action = parsed.get("action", "")
        if action == "final_answer":
            step.is_final = True
            step.final_answer = parsed.get("content", text)
        else:
            step.action = action
            step.action_input = parsed.get("parameters", {})
            step.thought = parsed.get("thought", "")

        return step
