"""Built-in shell command tool with allowlist enforcement. Requires approval."""

from __future__ import annotations

import shlex
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult
from plugins.sandbox import run_sandboxed

_ALLOWED_COMMANDS = {
    "ls", "cat", "echo", "pwd", "date", "df", "du", "free", "uptime",
    "ps", "top", "htop", "which", "find", "grep", "rg", "head", "tail",
    "wc", "sort", "uniq", "cut", "awk", "sed", "python3", "pip", "git",
    "curl", "wget", "tar", "gzip", "gunzip", "zip", "unzip", "md5sum",
    "sha256sum", "file", "stat", "env", "printenv", "systemctl", "journalctl",
}


class ShellTool(BaseTool):
    """
    Execute shell commands in a sandboxed subprocess.

    Only commands in the allowlist can be executed. Requires user approval.
    All executions are logged to the audit trail.
    """

    name = "shell"
    description = (
        "Execute a shell command. "
        "Only allowlisted commands are permitted. "
        "REQUIRES USER APPROVAL. All executions are audited."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "Shell command to execute (e.g., 'ls -la /home').",
            },
            "timeout_seconds": {
                "type": "number",
                "description": "Execution timeout. Default: 10.",
                "default": 10,
            },
        },
        "required": ["command"],
    }
    requires_approval = True
    timeout_seconds = 30

    async def dry_run(self, params: dict[str, Any]) -> str:
        cmd = params.get("command", "")
        return f"Will execute shell command: {cmd}"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        """Validate the command against the allowlist."""
        cmd = params.get("command", "")
        if not cmd:
            return ValidationResult.fail("command is required")
        try:
            parts = shlex.split(cmd)
        except ValueError as exc:
            return ValidationResult.fail(f"Invalid command syntax: {exc}")
        if not parts:
            return ValidationResult.fail("Empty command")
        base_cmd = parts[0].split("/")[-1]  # Get basename
        if base_cmd not in _ALLOWED_COMMANDS:
            return ValidationResult.fail(
                f"Command '{base_cmd}' is not in the allowlist. "
                f"Allowed: {sorted(_ALLOWED_COMMANDS)}"
            )
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Run the shell command in a sandbox.

        Args:
            params: Contains "command" and optional "timeout_seconds".
            context: Execution context with allowed_paths.

        Returns:
            ToolResult with command output.
        """
        cmd = params["command"]
        timeout = float(params.get("timeout_seconds", 10))
        parts = shlex.split(cmd)

        stdout, stderr, returncode = await run_sandboxed(
            command=parts,
            allowed_paths=context.allowed_paths,
            timeout_s=timeout,
        )

        output = stdout
        if stderr:
            output += f"\n[stderr]: {stderr}"

        if returncode != 0:
            return ToolResult.fail(output or f"Command failed with code {returncode}")

        return ToolResult.ok(output.strip(), returncode=returncode)
