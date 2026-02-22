"""AST-aware code parser for Python, and text-based for other languages."""

from __future__ import annotations

import ast
from pathlib import Path


def parse(path: str) -> str:
    """
    Extract a code file's content with structure annotations.

    For Python files: extracts docstrings and adds class/function headers.
    For Jupyter notebooks: extracts cell source text.
    For other languages: returns raw source with line numbers stripped.

    Args:
        path: Path to the source code file.

    Returns:
        Annotated source code text.
    """
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix == ".ipynb":
        return _parse_notebook(p)
    elif suffix == ".py":
        return _parse_python(p)
    else:
        return p.read_text(encoding="utf-8", errors="replace")


def _parse_python(p: Path) -> str:
    """Parse Python with AST-aware structure extraction."""
    source = p.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
        sections = [f"# File: {p.name}\n", source]
        # Add a structure summary as a comment block
        summary_lines = [f"# Structure of {p.name}:"]
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                indent = "  " if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else ""
                summary_lines.append(f"# {indent}{type(node).__name__}: {node.name} (line {node.lineno})")
        return "\n".join(summary_lines) + "\n\n" + source
    except SyntaxError:
        return source


def _parse_notebook(p: Path) -> str:
    """Extract code and markdown cells from a Jupyter notebook."""
    import json
    try:
        nb = json.loads(p.read_text(encoding="utf-8"))
        cells: list[str] = []
        for cell in nb.get("cells", []):
            cell_type = cell.get("cell_type", "")
            source = "".join(cell.get("source", []))
            if source.strip():
                prefix = "```python\n" if cell_type == "code" else ""
                suffix = "\n```" if cell_type == "code" else ""
                cells.append(f"{prefix}{source}{suffix}")
        return "\n\n".join(cells)
    except Exception as exc:
        return f"[Notebook parse error: {exc}]"
