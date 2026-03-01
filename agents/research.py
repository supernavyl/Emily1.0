"""ResearchAgent — deep-dive RAG + web search + synthesis."""

from __future__ import annotations

import asyncio
from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier
from observability.logger import get_logger

log = get_logger(__name__)


class ResearchAgent(BaseAgent):
    """
    Performs deep research combining RAG retrieval, web search, and LLM synthesis.

    Research pipeline:
    1. Query the memory system (semantic/episodic/knowledge) for relevant context
    2. Optionally search the web via the web_search tool
    3. Synthesize all sources into a comprehensive answer using the smart model
    """

    name = "ResearchAgent"
    description = "Deep research via RAG, web search, and synthesis."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()

    async def handle(self, message: Message) -> None:
        """Handle research task requests."""
        if message.type == "agent.task":
            await self._research(message)

    async def _retrieve_rag_context(self, task: str) -> str:
        """
        Query memory for relevant context using the hybrid retriever.

        Args:
            task: Research question or topic.

        Returns:
            Formatted RAG context block, or empty string if unavailable.
        """
        try:
            retriever = getattr(self._memory, "_retriever", None)
            if retriever is None:
                return ""

            results = await retriever.retrieve(task, top_k=5)
            if not results:
                return ""

            chunks = [{"content": r.content, "source": r.source, "score": r.score} for r in results]
            return self._prompts.build_rag_context_block(chunks)
        except Exception as exc:
            self._log.warning("research_rag_retrieval_failed", error=str(exc))
            return ""

    async def _web_search(self, task: str) -> str:
        """
        Search the web for supplementary information.

        Uses the built-in web_search tool via the plugin registry if available.

        Args:
            task: Search query.

        Returns:
            Web search results text, or empty string.
        """
        try:
            from plugins.registry import ToolRegistry

            registry = ToolRegistry()
            registry.load_builtins()
            tool = registry.get("web_search")
            if tool is None:
                return ""

            from plugins.base import ExecutionContext

            result = await tool.execute(
                {"query": task, "max_results": 3},
                ExecutionContext(),
            )
            return result.output if result.success else ""
        except Exception as exc:
            self._log.debug("research_web_search_unavailable", error=str(exc))
            return ""

    async def _research(self, message: Message) -> None:
        """
        Perform multi-source research and return synthesized findings.

        Pipeline: RAG retrieval + web search (parallel) -> LLM synthesis.

        Args:
            message: Contains "task" and optional "plan_id", "step_index".
        """
        task = message.payload.get("task", "")
        plan_id = message.payload.get("plan_id")
        step_index = message.payload.get("step_index", 0)

        rag_context, web_results = await asyncio.gather(
            self._retrieve_rag_context(task),
            self._web_search(task),
            return_exceptions=True,
        )

        if isinstance(rag_context, BaseException):
            rag_context = ""
        if isinstance(web_results, BaseException):
            web_results = ""

        research_prompt = self._prompts.build_research_prompt(task)

        context_parts: list[str] = []
        if rag_context:
            context_parts.append(f"KNOWLEDGE BASE RESULTS:\n{rag_context}")
        if web_results:
            context_parts.append(f"WEB SEARCH RESULTS:\n{web_results}")

        full_prompt = research_prompt
        if context_parts:
            full_prompt = "\n\n".join(context_parts) + "\n\n" + research_prompt

        result = await self._fleet.chat(
            user_message=task,
            messages=[ChatMessage(role="user", content=full_prompt)],
            force_tier=ModelTier.SMART,
        )

        self._log.info(
            "research_complete",
            task=task[:60],
            has_rag=bool(rag_context),
            has_web=bool(web_results),
        )

        if plan_id:
            await self.send(
                "PlannerAgent",
                "planner.subtask_result",
                {
                    "plan_id": plan_id,
                    "step_index": step_index,
                    "result": result.content,
                    "task": task,
                },
                priority=Priority.ACTIVE,
                task_id=message.task_id,
            )
