"""
Base tool interface for Emily's plugin system.

All tools — built-in and generated — must subclass BaseTool.
The interface enforces:
- Typed parameters (JSON Schema)
- dry_run() implementation before execute()
- Optional human-in-the-loop approval gate
- Structured ToolResult return type
- Timeout and rate limiting metadata
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standardized result from a tool execution."""

    success: bool
    output: Any
    error: str | None = None
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, output: Any, execution_time_ms: float = 0.0, **metadata: Any) -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output, execution_time_ms=execution_time_ms, metadata=metadata)

    @classmethod
    def fail(cls, error: str, execution_time_ms: float = 0.0) -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, output=None, error=error, execution_time_ms=execution_time_ms)


@dataclass
class ValidationResult:
    """Result of parameter validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True)

    @classmethod
    def fail(cls, *errors: str) -> "ValidationResult":
        return cls(valid=False, errors=list(errors))


@dataclass
class ExecutionContext:
    """
    Context passed to every tool execution.

    Provides access to Emily's memory, config, and session info
    without creating circular imports.
    """

    session_id: str
    user_id: str = "default"
    allowed_paths: list[str] = field(default_factory=list)
    sandbox_enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RateLimit:
    """Rate limiting specification for a tool."""

    calls_per_minute: int = 60
    calls_per_hour: int = 600


class BaseTool(ABC):
    """
    Abstract base class for all Emily tools.

    Subclasses must implement:
    - name (class attribute)
    - description (class attribute)
    - parameters (class attribute, JSON Schema dict)
    - execute()
    - dry_run()

    Subclasses should override:
    - validate() for custom parameter validation
    - requires_approval (if True, user must confirm before execution)
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {}
    requires_approval: bool = False
    timeout_seconds: int = 30
    rate_limit: RateLimit = field(default_factory=RateLimit)

    @abstractmethod
    async def execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """
        Execute the tool with the given parameters.

        Args:
            params: Tool parameters matching the JSON Schema.
            context: Execution context with session info and sandbox settings.

        Returns:
            ToolResult with success/failure and output.
        """
        ...

    @abstractmethod
    async def dry_run(self, params: dict[str, Any]) -> str:
        """
        Explain what this tool would do without executing it.

        Args:
            params: Tool parameters.

        Returns:
            Human-readable description of the planned action.
        """
        ...

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        """
        Validate tool parameters before execution.

        Default implementation checks required fields from the JSON Schema.
        Override for custom validation logic.

        Args:
            params: Parameters to validate.

        Returns:
            ValidationResult with any errors.
        """
        required = self.parameters.get("required", [])
        missing = [r for r in required if r not in params]
        if missing:
            return ValidationResult.fail(f"Missing required parameters: {missing}")
        return ValidationResult.ok()

    def to_schema(self) -> dict[str, Any]:
        """
        Return the tool's JSON Schema for LLM tool-calling prompts.

        Returns:
            Dict with name, description, and parameters.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "requires_approval": self.requires_approval,
        }

    async def safe_execute(
        self,
        params: dict[str, Any],
        context: ExecutionContext,
    ) -> ToolResult:
        """
        Validate and execute with timing and error handling.

        Args:
            params: Tool parameters.
            context: Execution context.

        Returns:
            ToolResult.
        """
        validation = await self.validate(params)
        if not validation.valid:
            return ToolResult.fail(f"Validation failed: {'; '.join(validation.errors)}")

        t0 = time.monotonic()
        try:
            result = await self.execute(params, context)
            result.execution_time_ms = (time.monotonic() - t0) * 1000.0
            return result
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000.0
            return ToolResult.fail(str(exc), execution_time_ms=elapsed)
