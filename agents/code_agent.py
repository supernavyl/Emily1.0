"""CodeAgent — code generation, sandboxed execution, and debugging."""

from __future__ import annotations

import re
from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier, TaskType
from observability.logger import get_logger

log = get_logger(__name__)


class CodeAgent(BaseAgent):
    """
    Generates code via LLM and executes it in the bubblewrap sandbox.

    Pipeline:
    1. LLM generates code for the task using the smart model
    2. Code blocks are extracted from the response
    3. Python code is executed in ``plugins.sandbox.run_python_sandboxed``
    4. Execution output is appended to the result
    """

    name = "CodeAgent"
    description = "Writes, tests, and debugs code in a sandboxed executor."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()

    async def handle(self, message: Message) -> None:
        """Handle code tasks."""
        if message.type in ("agent.task", "code.request"):
            await self._handle_code_task(message)

    @staticmethod
    def _extract_code_blocks(text: str, language: str = "python") -> list[str]:
        """
        Extract fenced code blocks from LLM output.

        Args:
            text: LLM response text potentially containing code fences.
            language: Target language to look for.

        Returns:
            List of code strings extracted from fences.
        """
        pattern = rf"```(?:{language})?\s*\n(.*?)```"
        blocks = re.findall(pattern, text, re.DOTALL)
        return [b.strip() for b in blocks if b.strip()]

    async def _run_sandboxed(self, code: str) -> str:
        """
        Execute Python code in the bubblewrap sandbox.

        Args:
            code: Python source code to execute.

        Returns:
            Execution stdout/stderr or error message.
        """
        try:
            from plugins.sandbox import run_python_sandboxed

            result = await run_python_sandboxed(code, timeout=30)
            return result.output if result.success else f"Error: {result.output}"
        except Exception as exc:
            return f"Sandbox execution failed: {exc}"

    async def _handle_code_task(self, message: Message) -> None:
        """
        Generate code, optionally execute it in sandbox, and return results.

        Args:
            message: Contains "task" with code-related request.
        """
        task = message.payload.get("task", "")
        plan_id = message.payload.get("plan_id")
        step_index = message.payload.get("step_index", 0)
        language = message.payload.get("language", "python")
        execute = message.payload.get("execute", True)

        code_prompt = self._prompts.build_code_generation_prompt(task, language)

        result = await self._fleet.chat(
            user_message=task,
            messages=[ChatMessage(role="user", content=code_prompt)],
            force_tier=ModelTier.SMART,
            task_type=TaskType.CODE,
        )

        generated = result.content
        self._log.info("code_generated", task=task[:60], language=language)

        execution_output = ""
        if execute and language == "python":
            blocks = self._extract_code_blocks(generated, language)
            if blocks:
                execution_output = await self._run_sandboxed(blocks[0])
                self._log.info(
                    "code_executed",
                    output_len=len(execution_output),
                    success="Error" not in execution_output,
                )

        final_result = generated
        if execution_output:
            final_result += f"\n\n--- Execution Output ---\n{execution_output}"

        if plan_id:
            await self.send(
                "PlannerAgent",
                "planner.subtask_result",
                {
                    "plan_id": plan_id,
                    "step_index": step_index,
                    "result": final_result,
                    "task": task,
                },
                priority=Priority.ACTIVE,
                task_id=message.task_id,
            )
