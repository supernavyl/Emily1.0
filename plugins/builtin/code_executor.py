"""Built-in Python code executor with sandboxed subprocess."""

from __future__ import annotations

from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult
from plugins.sandbox import run_python_sandboxed


class CodeExecutorTool(BaseTool):
    """
    Execute Python code in a restricted sandbox and return stdout/stderr.

    The code runs in a bubblewrap container with no network access and
    limited filesystem access. Execution is time-limited.
    """

    name = "code_executor"
    description = (
        "Execute Python code in a secure sandbox. "
        "Returns stdout output and any errors. "
        "No network access. Filesystem access limited to allowed paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute.",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Execution timeout in seconds. Default: 10.",
                "default": 10,
            },
        },
        "required": ["code"],
    }
    requires_approval = False
    timeout_seconds = 30

    async def dry_run(self, params: dict[str, Any]) -> str:
        """Show what code would be executed."""
        code_preview = params.get("code", "")[:200]
        return f"Will execute Python code in sandbox:\n```python\n{code_preview}\n```"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Run Python code in a sandboxed subprocess.

        Args:
            params: Contains "code" and optional "timeout_seconds".
            context: Execution context with allowed paths.

        Returns:
            ToolResult with combined stdout, stderr, and return code.
        """
        code = params["code"]
        timeout = float(params.get("timeout_seconds", 10))

        stdout, stderr, returncode = await run_python_sandboxed(
            code=code,
            allowed_paths=context.allowed_paths,
            timeout_s=timeout,
        )

        output = stdout
        if stderr:
            output += f"\n[stderr]: {stderr}"

        if returncode != 0 and not stdout:
            return ToolResult.fail(stderr or "Execution failed with no output")

        return ToolResult.ok(
            output=output.strip(),
            returncode=returncode,
            had_errors=bool(stderr),
        )
