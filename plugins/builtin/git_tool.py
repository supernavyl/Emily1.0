"""Built-in Git operations tool."""

from __future__ import annotations

from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult
from plugins.sandbox import run_sandboxed

_GIT_SUBCOMMANDS = {"status", "log", "diff", "show", "branch", "tag", "remote"}


class GitTool(BaseTool):
    """Safe read-only Git operations (status, log, diff, etc.)."""

    name = "git_tool"
    description = (
        "Run read-only Git commands on local repositories. "
        "Supported: status, log, diff, show, branch, tag, remote."
    )
    parameters = {
        "type": "object",
        "properties": {
            "repo_path": {"type": "string", "description": "Path to the git repository."},
            "subcommand": {
                "type": "string",
                "description": f"Git subcommand: {', '.join(sorted(_GIT_SUBCOMMANDS))}.",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Additional arguments (e.g., ['--oneline', '-10']).",
                "default": [],
            },
        },
        "required": ["repo_path", "subcommand"],
    }
    requires_approval = False
    timeout_seconds = 15

    async def dry_run(self, params: dict[str, Any]) -> str:
        subcmd = params.get("subcommand", "")
        args = " ".join(params.get("args", []))
        return f"Will run: git {subcmd} {args} in {params.get('repo_path', '')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Execute a read-only git command.

        Args:
            params: Contains "repo_path", "subcommand", optional "args".
            context: Execution context.

        Returns:
            ToolResult with git output.
        """
        subcmd = params["subcommand"]
        if subcmd not in _GIT_SUBCOMMANDS:
            return ToolResult.fail(
                f"Subcommand '{subcmd}' not allowed. Use: {sorted(_GIT_SUBCOMMANDS)}"
            )

        repo = params["repo_path"]
        args = params.get("args", [])
        command = ["git", "-C", repo, subcmd] + [str(a) for a in args]

        stdout, stderr, code = await run_sandboxed(
            command=command,
            allowed_paths=context.allowed_paths + [repo],
            timeout_s=self.timeout_seconds,
        )
        if code != 0:
            return ToolResult.fail(stderr or stdout)
        return ToolResult.ok(stdout.strip())
