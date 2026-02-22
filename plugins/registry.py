"""
Plugin registry for Emily's tool ecosystem.

Manages discovery, registration, and lookup of all available tools.
Built-in tools are auto-registered at startup. Generated tools (from
ToolBuilderAgent) are registered dynamically after user approval.

The registry is the single source of truth for what tools Emily can use.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Any

from observability.logger import get_logger
from plugins.base import BaseTool

log = get_logger(__name__)

_BUILTIN_MODULES = [
    "plugins.builtin.calculator",
    "plugins.builtin.code_executor",
    "plugins.builtin.file_ops",
    "plugins.builtin.web_search",
    "plugins.builtin.web_fetch",
    "plugins.builtin.shell",
    "plugins.builtin.git_tool",
    "plugins.builtin.calendar",
    "plugins.builtin.home_assistant",
    "plugins.builtin.image_analyzer",
    "plugins.builtin.notification",
    "plugins.builtin.process_manager",
    "plugins.builtin.email_reader",
    "plugins.builtin.singing",
]


class PluginRegistry:
    """
    Central registry for all Emily tool plugins.

    Provides lookup by name, schema enumeration for LLM prompts,
    and dynamic loading of generated tools.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool instance.

        Args:
            tool: The tool to register. Its `name` attribute is used as key.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            log.warning("tool_already_registered_overwriting", name=tool.name)
        self._tools[tool.name] = tool
        log.debug("tool_registered", name=tool.name)

    def get(self, name: str) -> BaseTool | None:
        """
        Look up a tool by name.

        Args:
            name: Tool name.

        Returns:
            BaseTool instance, or None if not found.
        """
        return self._tools.get(name)

    def all_tools(self) -> list[BaseTool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def all_schemas(self) -> list[dict[str, Any]]:
        """
        Return JSON Schema dicts for all registered tools.

        Used to build the tool-calling section of LLM prompts.

        Returns:
            List of tool schema dicts.
        """
        return [t.to_schema() for t in self._tools.values()]

    def load_builtins(
        self,
        tool_kwargs: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """
        Auto-discover and register all built-in tools.

        Imports each module in _BUILTIN_MODULES and instantiates any
        BaseTool subclasses found in the module's namespace.

        Args:
            tool_kwargs: Optional mapping of tool *name* to keyword arguments
                         passed to that tool's constructor.  For example::

                             {"web_search": {"searxng_url": "http://localhost:8080"}}
        """
        overrides = tool_kwargs or {}
        for module_path in _BUILTIN_MODULES:
            try:
                module = importlib.import_module(module_path)
                self._register_from_module(module, overrides)
            except ImportError as exc:
                log.warning(
                    "builtin_tool_import_failed",
                    module=module_path,
                    error=str(exc),
                )
            except Exception as exc:
                log.error(
                    "builtin_tool_load_error",
                    module=module_path,
                    error=str(exc),
                )

    def load_generated(self, path: str) -> bool:
        """
        Load a generated tool from a Python file path.

        This is called after the user approves a ToolBuilderAgent-generated tool.

        Args:
            path: Absolute path to the generated tool Python file.

        Returns:
            True if at least one tool was loaded successfully.
        """
        file_path = Path(path)
        if not file_path.exists():
            log.error("generated_tool_file_not_found", path=path)
            return False

        spec = importlib.util.spec_from_file_location(
            f"generated_{file_path.stem}", file_path
        )
        if spec is None or spec.loader is None:
            log.error("generated_tool_spec_failed", path=path)
            return False

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            log.error("generated_tool_exec_failed", path=path, error=str(exc))
            return False

        n_loaded = self._register_from_module(module)
        log.info("generated_tool_loaded", path=path, n_tools=n_loaded)
        return n_loaded > 0

    def _register_from_module(
        self,
        module: object,
        overrides: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        """
        Find and register all BaseTool subclasses in a module.

        Args:
            module: Imported Python module.
            overrides: Mapping of tool name to constructor kwargs.

        Returns:
            Number of tools registered from this module.
        """
        overrides = overrides or {}
        n = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseTool)
                and attr is not BaseTool
                and attr.name  # Must have a name set
            ):
                try:
                    kwargs = overrides.get(attr.name, {})
                    instance = attr(**kwargs)
                    self.register(instance)
                    n += 1
                except Exception as exc:
                    log.warning(
                        "tool_instantiation_failed",
                        tool=attr_name,
                        error=str(exc),
                    )
        return n

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
