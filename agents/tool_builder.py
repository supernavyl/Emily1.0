"""
ToolBuilderAgent — Emily writes her own tools at runtime.

When Emily encounters a capability gap (logged in data/capability_gaps.jsonl),
the ToolBuilderAgent:
1. Reads the gap description
2. Drafts a BaseTool subclass using the smart model
3. Statically analyzes the generated code (AST scan)
4. Presents the code to the user for review (diff view in TUI/web)
5. On approval: saves to plugins/generated/ and loads it at runtime

All generated tools run in the bubblewrap sandbox regardless.
"""

from __future__ import annotations

import ast
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from agents.base import BaseAgent
from core.bus import Message, Priority
from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier
from observability.logger import get_logger

log = get_logger(__name__)

_DANGEROUS_PATTERNS = {
    "os.system",
    "subprocess.Popen",
    "subprocess.call",
    "__import__",
    "exec(",
    "eval(",
    "socket.",
    "requests.",
    "urllib",
}

_TOOL_TEMPLATE = '''"""Generated tool: {name}. Created by ToolBuilderAgent on {date}."""

from __future__ import annotations
from typing import Any
from plugins.base import BaseTool, ExecutionContext, ToolResult


class {class_name}(BaseTool):
    """{description}"""

    name = "{tool_name}"
    description = "{description}"
    parameters = {parameters}
    requires_approval = {requires_approval}
    timeout_seconds = 30

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Will execute: {description}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        try:
{execute_body}
        except Exception as exc:
            return ToolResult.fail(str(exc))
'''


class ToolBuilderAgent(BaseAgent):
    """
    Generates new BaseTool subclasses to fill detected capability gaps.

    The generated code is never auto-loaded — it always requires explicit
    user approval via the consent gate before becoming available.
    """

    name = "ToolBuilderAgent"
    description = "Generates new tools to fill capability gaps. Requires user approval."

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._prompts = PromptBuilder()
        self._pending_approvals: dict[str, dict[str, Any]] = {}

    async def handle(self, message: Message) -> None:
        """Handle tool building and approval messages."""
        handlers = {
            "toolbuilder.build_request": self._build_tool,
            "toolbuilder.approved": self._load_approved_tool,
            "toolbuilder.rejected": self._handle_rejection,
            "toolbuilder.scan_gaps": self._scan_capability_gaps,
        }
        handler = handlers.get(message.type)
        if handler:
            await handler(message)

    async def _scan_capability_gaps(self, message: Message) -> None:
        """
        Read capability_gaps.jsonl and trigger tool building for recent gaps.

        Args:
            message: Trigger message (payload unused).
        """
        gap_log = Path("data/capability_gaps.jsonl")
        if not gap_log.exists():
            return

        def _read_gaps() -> list[dict[str, Any]]:
            items: list[dict[str, Any]] = []
            with gap_log.open() as f:
                for line in f:
                    try:
                        items.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
            return items

        gaps = await asyncio.to_thread(_read_gaps)

        # Process the 3 most recent gaps
        recent = sorted(gaps, key=lambda g: g.get("timestamp", 0), reverse=True)[:3]
        for gap in recent:
            await self._build_for_gap(gap.get("gap", ""), gap.get("source", "unknown"))

    async def _build_for_gap(self, gap: str, source: str) -> None:
        """
        Generate a tool to address a capability gap.

        Args:
            gap: Description of the missing capability.
            source: Where the gap was detected.
        """
        self._log.info("building_tool_for_gap", gap=gap[:60])

        generation_prompt = self._prompts.build_tool_generation_prompt(gap)

        result = await self._fleet.chat(
            user_message=generation_prompt,
            messages=[ChatMessage(role="user", content=generation_prompt)],
            force_tier=ModelTier.SMART,
            temperature=0.3,
        )

        code = result.content.strip()
        if not code:
            return

        # Static analysis
        issues = self._analyze_code(code)
        if any("CRITICAL" in i for i in issues):
            self._log.warning("generated_tool_blocked_dangerous_code", issues=issues)
            return

        # Save to pending and notify for approval
        approval_id = str(uuid.uuid4())
        preview_path = Path(f"plugins/generated/pending_{approval_id}.py")
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(preview_path.write_text, code)

        self._pending_approvals[approval_id] = {
            "code": code,
            "gap": gap,
            "source": source,
            "path": str(preview_path),
            "issues": issues,
            "created_at": time.time(),
        }

        self._log.info(
            "tool_pending_approval",
            approval_id=approval_id,
            path=str(preview_path),
            issues=issues,
        )

        # Notify ConversationAgent to present to user
        await self.send(
            "ConversationAgent",
            "text.input",
            {
                "text": (
                    f"I've drafted a new tool to help with: {gap}\n\n"
                    f"Code preview: {preview_path!s}\n"
                    f"Analysis: "
                    f"{'; '.join(issues) if issues else 'No issues detected.'}"
                    f"\n\nReply 'approve {approval_id}' to load "
                    f"this tool, or 'reject {approval_id}' to discard."
                )
            },
            priority=Priority.ACTIVE,
        )

    async def _build_tool(self, message: Message) -> None:
        """Manual tool build request."""
        gap = message.payload.get("gap", "")
        source = message.payload.get("source", "manual")
        if gap:
            await self._build_for_gap(gap, source)

    async def _load_approved_tool(self, message: Message) -> None:
        """
        Load a user-approved generated tool into the plugin registry.

        Args:
            message: Contains "approval_id".
        """
        approval_id = message.payload.get("approval_id", "")
        if approval_id not in self._pending_approvals:
            self._log.warning("unknown_approval_id", approval_id=approval_id)
            return

        pending = self._pending_approvals[approval_id]
        final_path = Path(f"plugins/generated/tool_{approval_id[:8]}.py")
        await asyncio.to_thread(final_path.write_text, pending["code"])

        # Remove pending file
        await asyncio.to_thread(Path(pending["path"]).unlink, True)
        del self._pending_approvals[approval_id]

        self._log.info("generated_tool_approved_and_saved", path=str(final_path))

        # Notify that a new tool is available for loading
        await self.send(
            "ConversationAgent",
            "text.input",
            {
                "text": (
                    f"Tool approved and saved to {final_path}. "
                    "It will be available after the next registry refresh."
                ),
            },
            priority=Priority.ACTIVE,
        )

    async def _handle_rejection(self, message: Message) -> None:
        """Handle tool rejection — clean up pending file."""
        approval_id = message.payload.get("approval_id", "")
        if approval_id in self._pending_approvals:
            pending = self._pending_approvals[approval_id]
            Path(pending["path"]).unlink(missing_ok=True)
            del self._pending_approvals[approval_id]
            self._log.info("generated_tool_rejected", approval_id=approval_id)

    def _analyze_code(self, code: str) -> list[str]:
        """
        Perform static analysis on generated tool code.

        Checks for:
        - Dangerous patterns (subprocess, os.system, eval, etc.)
        - Syntax errors
        - Missing required methods

        Args:
            code: Python source code string.

        Returns:
            List of issue strings (empty = clean).
        """
        issues: list[str] = []

        # Syntax check
        try:
            ast.parse(code)
        except SyntaxError as exc:
            issues.append(f"CRITICAL: Syntax error at line {exc.lineno}: {exc.msg}")
            return issues  # No point continuing if code doesn't parse

        # Dangerous pattern check
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in code:
                issues.append(f"CRITICAL: Dangerous pattern detected: {pattern}")

        # Required methods check
        for method in ("execute", "dry_run"):
            if f"def {method}" not in code and f"async def {method}" not in code:
                issues.append(f"WARNING: Missing required method: {method}")

        return issues
