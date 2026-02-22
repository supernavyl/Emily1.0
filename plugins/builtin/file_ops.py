"""Built-in file read/write tools with path allowlist enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult


def _is_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    """Check if the given path is within one of the allowed directories."""
    resolved = Path(path).resolve()
    for allowed in allowed_paths:
        if resolved.is_relative_to(Path(allowed).resolve()):
            return True
    return False


class FileReaderTool(BaseTool):
    """Read the contents of a file within allowed paths."""

    name = "file_reader"
    description = (
        "Read the contents of a file. "
        "Only files within configured allowed paths can be read."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path to read."},
            "encoding": {"type": "string", "description": "File encoding. Default: utf-8.", "default": "utf-8"},
            "max_bytes": {"type": "integer", "description": "Maximum bytes to read. Default: 1MB.", "default": 1048576},
        },
        "required": ["path"],
    }
    requires_approval = False
    timeout_seconds = 5

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will read file: {params.get('path', '')}"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        path = params.get("path", "")
        if not path:
            return ValidationResult.fail("path is required")
        if not Path(path).exists():
            return ValidationResult.fail(f"File not found: {path}")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Read file contents, enforcing the path allowlist.

        Args:
            params: Contains "path", optional "encoding" and "max_bytes".
            context: Execution context with allowed_paths.

        Returns:
            ToolResult with file contents as string.
        """
        path = params["path"]
        encoding = params.get("encoding", "utf-8")
        max_bytes = int(params.get("max_bytes", 1048576))

        if not _is_path_allowed(path, context.allowed_paths):
            return ToolResult.fail(f"Path not in allowed list: {path}")

        try:
            p = Path(path)
            size = p.stat().st_size
            if size > max_bytes:
                content = p.read_bytes()[:max_bytes].decode(encoding, errors="replace")
                return ToolResult.ok(
                    content,
                    truncated=True,
                    bytes_read=max_bytes,
                    total_bytes=size,
                )
            content = p.read_text(encoding=encoding)
            return ToolResult.ok(content, bytes_read=size)
        except Exception as exc:
            return ToolResult.fail(str(exc))


class FileWriterTool(BaseTool):
    """Write content to a file within allowed paths. Requires approval."""

    name = "file_writer"
    description = (
        "Write content to a file. "
        "Only files within configured allowed paths can be written. "
        "REQUIRES USER APPROVAL before writing."
    )
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write to."},
            "content": {"type": "string", "description": "Content to write."},
            "encoding": {"type": "string", "description": "File encoding. Default: utf-8.", "default": "utf-8"},
            "mode": {
                "type": "string",
                "description": "Write mode: 'overwrite' or 'append'. Default: overwrite.",
                "default": "overwrite",
            },
        },
        "required": ["path", "content"],
    }
    requires_approval = True
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        mode = params.get("mode", "overwrite")
        content_preview = str(params.get("content", ""))[:100]
        return (
            f"Will {mode} file: {params.get('path', '')}\n"
            f"Content preview: {content_preview}{'...' if len(str(params.get('content', ''))) > 100 else ''}"
        )

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Write to a file, enforcing path allowlist.

        Args:
            params: Contains "path", "content", optional "encoding" and "mode".
            context: Execution context with allowed_paths.

        Returns:
            ToolResult indicating success or failure.
        """
        path = params["path"]
        content = params["content"]
        encoding = params.get("encoding", "utf-8")
        mode = params.get("mode", "overwrite")

        if not _is_path_allowed(path, context.allowed_paths):
            return ToolResult.fail(f"Path not in allowed list: {path}")

        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            if mode == "append":
                with p.open("a", encoding=encoding) as f:
                    f.write(content)
            else:
                p.write_text(content, encoding=encoding)
            return ToolResult.ok(f"Written {len(content)} chars to {path}")
        except Exception as exc:
            return ToolResult.fail(str(exc))
