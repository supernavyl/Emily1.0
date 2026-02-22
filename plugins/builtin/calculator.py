"""Built-in calculator tool using sympy for symbolic math."""

from __future__ import annotations

from typing import Any

from plugins.base import BaseTool, ExecutionContext, ToolResult

try:
    import sympy  # type: ignore[import-untyped]
    _SYMPY_AVAILABLE = True
except ImportError:
    _SYMPY_AVAILABLE = False


class CalculatorTool(BaseTool):
    """
    Symbolic math calculator powered by sympy.

    Supports arithmetic, algebra, calculus (derivatives, integrals),
    equation solving, and unit conversions.
    """

    name = "calculator"
    description = (
        "Evaluate mathematical expressions, solve equations, "
        "compute derivatives/integrals, and perform symbolic algebra. "
        "Input is a Python/SymPy expression string."
    )
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression or equation to evaluate. "
                               "Examples: '2 + 2', 'solve(x**2 - 4, x)', 'diff(sin(x), x)'",
            }
        },
        "required": ["expression"],
    }
    requires_approval = False
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        """Describe what would be computed."""
        return f"Will evaluate the expression: {params.get('expression', '')}"

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        """
        Evaluate a mathematical expression using sympy.

        Args:
            params: Must contain "expression" key.
            context: Execution context (unused for calculator).

        Returns:
            ToolResult with the computed result as a string.
        """
        expr = params["expression"]

        if _SYMPY_AVAILABLE:
            return await self._sympy_eval(expr)
        else:
            return await self._safe_eval(expr)

    async def _sympy_eval(self, expr: str) -> ToolResult:
        """Evaluate using sympy for full symbolic math support."""
        import asyncio
        import sympy
        from sympy import symbols, solve, diff, integrate, simplify, expand, factor

        def _compute() -> str:
            namespace = {
                "symbols": symbols,
                "solve": solve,
                "diff": diff,
                "integrate": integrate,
                "simplify": simplify,
                "expand": expand,
                "factor": factor,
                "x": symbols("x"),
                "y": symbols("y"),
                "z": symbols("z"),
                "n": symbols("n"),
            }
            # Allow basic sympy functions
            from sympy import (sin, cos, tan, exp, log, sqrt, pi, E,
                               oo, Rational, factorial)
            namespace.update({
                "sin": sin, "cos": cos, "tan": tan, "exp": exp,
                "log": log, "sqrt": sqrt, "pi": pi, "E": E,
                "oo": oo, "Rational": Rational, "factorial": factorial,
            })
            result = eval(expr, {"__builtins__": {}}, namespace)  # noqa: S307
            return str(result)

        try:
            result = await asyncio.to_thread(_compute)
            return ToolResult.ok(result)
        except Exception as exc:
            return ToolResult.fail(f"Calculation error: {exc}")

    async def _safe_eval(self, expr: str) -> ToolResult:
        """Fallback: evaluate simple arithmetic with Python's eval."""
        import ast
        try:
            tree = ast.parse(expr, mode="eval")
            # Only allow safe node types
            for node in ast.walk(tree):
                if not isinstance(node, (
                    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num,
                    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
                    ast.Mod, ast.FloorDiv, ast.USub, ast.UAdd,
                    ast.Constant, ast.Load,
                )):
                    return ToolResult.fail(f"Unsafe expression: {type(node).__name__}")
            result = eval(compile(tree, "<expr>", "eval"))  # noqa: S307
            return ToolResult.ok(str(result))
        except Exception as exc:
            return ToolResult.fail(f"Calculation error: {exc}")
