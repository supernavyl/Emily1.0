"""Computer launcher tool — open files, URLs, apps, and folders on the desktop.

Uses xdg-open (Linux standard) to delegate to the user's configured default
application for each MIME type. For app launching by name, searches:
  1. /usr/share/applications and ~/.local/share/applications (.desktop files)
  2. PATH (for CLI or GUI app binaries directly)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from pathlib import Path
from typing import Any

from observability.logger import get_logger
from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult

log = get_logger(__name__)

_DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
]


def _find_app_binary(name: str) -> str | None:
    """Return the binary path for an app name, or None."""
    return shutil.which(name)


def _find_desktop_file(name: str) -> Path | None:
    """Search .desktop files for an app by name or Name= field."""
    name_lower = name.lower().replace(" ", "-")
    for desktop_dir in _DESKTOP_DIRS:
        if not desktop_dir.exists():
            continue
        for desktop in desktop_dir.glob("*.desktop"):
            stem = desktop.stem.lower()
            if name_lower in stem or stem in name_lower:
                return desktop
            # Check the Name= field inside the file
            try:
                text = desktop.read_text(errors="replace")
                for line in text.splitlines():
                    if line.startswith("Name=") and name_lower in line.lower():
                        return desktop
            except OSError:
                continue
    return None


def _resolve_target(target: str) -> tuple[str, str]:
    """Return (resolved_target, kind) where kind is file|url|app|folder|desktop|unknown."""
    # URLs
    if target.startswith(("http://", "https://", "ftp://", "mailto:", "file://")):
        return target, "url"

    path = Path(target).expanduser().resolve()

    # Existing filesystem path
    if path.exists():
        if path.is_dir():
            return str(path), "folder"
        return str(path), "file"

    # Try app lookup — binary in PATH
    binary = _find_app_binary(target)
    if binary:
        return binary, "app"

    # Try .desktop file lookup
    desktop = _find_desktop_file(target)
    if desktop:
        return str(desktop), "desktop"

    # Bare word with a colon might be a custom URL scheme (e.g. "spotify:track:…")
    if ":" in target:
        return target, "url"

    return target, "unknown"


class ComputerOpenTool(BaseTool):
    """Open a file, URL, folder, or application on the host desktop."""

    name = "computer_open"
    description = (
        "Open anything on the computer — a file, folder, URL, or application — "
        "using the system default handler (xdg-open on Linux). "
        "Examples: open a PDF, launch a browser tab, open the Downloads folder, "
        "start an application like 'firefox', 'code', 'spotify', or 'nautilus'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "description": (
                    "What to open. Can be:\n"
                    "  - A file path: /home/user/docs/report.pdf\n"
                    "  - A URL: https://example.com\n"
                    "  - A folder: ~/Downloads\n"
                    "  - An app name: firefox, code, spotify, nautilus, discord"
                ),
            },
            "background": {
                "type": "boolean",
                "description": "Launch detached from Emily's process (default: true).",
                "default": True,
            },
        },
        "required": ["target"],
    }
    requires_approval = False
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        target = params.get("target", "")
        resolved, kind = _resolve_target(target)
        return f"Will open {kind}: {resolved}"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        target = params.get("target", "").strip()
        if not target:
            return ValidationResult.fail("target is required")
        if not shutil.which("xdg-open"):
            return ValidationResult.fail("xdg-open not found — cannot open items on this system")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        target = params.get("target", "").strip()
        background: bool = params.get("background", True)
        t0 = time.monotonic()

        resolved, kind = _resolve_target(target)
        log.info("computer_open", target=target, resolved=resolved, kind=kind)

        # For .desktop files use gtk-launch if available, otherwise xdg-open
        if kind == "desktop":
            stem = Path(resolved).stem
            cmd = ["gtk-launch", stem] if shutil.which("gtk-launch") else ["xdg-open", resolved]
        elif kind == "app":
            # Direct binary — launch detached
            cmd = [resolved]
        else:
            cmd = ["xdg-open", resolved]

        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}

        try:
            if background:
                # Fire-and-forget: start_new_session detaches from Emily's process group
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=True,
                    env=env,
                )
                elapsed = (time.monotonic() - t0) * 1000
                return ToolResult.ok(
                    output=f"Opened {kind}: {resolved}",
                    execution_time_ms=elapsed,
                    kind=kind,
                    resolved=resolved,
                    pid=proc.pid,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=self.timeout_seconds
                    )
                except TimeoutError:
                    proc.kill()
                    elapsed = (time.monotonic() - t0) * 1000
                    return ToolResult.fail(
                        error=f"Timed out opening: {resolved}",
                        execution_time_ms=elapsed,
                    )

                elapsed = (time.monotonic() - t0) * 1000
                if proc.returncode == 0:
                    return ToolResult.ok(
                        output=f"Opened {kind}: {resolved}",
                        execution_time_ms=elapsed,
                        kind=kind,
                        resolved=resolved,
                    )
                err_msg = (
                    stderr.decode(errors="replace").strip()
                    or f"xdg-open exited with code {proc.returncode}"
                )
                return ToolResult.fail(error=err_msg, execution_time_ms=elapsed)

        except FileNotFoundError as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(error=f"Command not found: {exc}", execution_time_ms=elapsed)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            log.error("computer_open_error", error=str(exc))
            return ToolResult.fail(error=str(exc), execution_time_ms=elapsed)


class AppLaunchTool(BaseTool):
    """Launch a named desktop application by searching .desktop files and PATH."""

    name = "app_launch"
    description = (
        "Launch a desktop application by name. More targeted than computer_open — "
        "searches installed .desktop entries and PATH binaries. "
        "Supports optional arguments. Examples: 'firefox', 'code', 'discord', 'obs', 'gimp', 'vlc'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "app": {
                "type": "string",
                "description": "Application name to launch (e.g., 'firefox', 'code', 'spotify').",
            },
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional command-line arguments to pass to the application.",
                "default": [],
            },
        },
        "required": ["app"],
    }
    requires_approval = False
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will launch application: {params.get('app', '')}"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        app = params.get("app", "").strip()
        if not app:
            return ValidationResult.fail("app is required")
        binary = _find_app_binary(app)
        desktop = _find_desktop_file(app)
        if not binary and not desktop:
            return ValidationResult.fail(f"Application not found: {app!r}")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        app = params.get("app", "").strip()
        extra_args: list[str] = params.get("args", [])
        t0 = time.monotonic()

        binary = _find_app_binary(app)
        desktop = _find_desktop_file(app)

        if binary:
            cmd = [binary, *extra_args]
            label = f"binary:{binary}"
        elif desktop:
            stem = desktop.stem
            cmd = ["gtk-launch", stem] if shutil.which("gtk-launch") else ["xdg-open", str(desktop)]
            label = f"desktop:{stem}"
        else:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(
                error=f"Application not found: {app!r}", execution_time_ms=elapsed
            )

        env = {**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
                env=env,
            )
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.ok(
                output=f"Launched {app} ({label})",
                execution_time_ms=elapsed,
                app=app,
                label=label,
                pid=proc.pid,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            log.error("app_launch_error", app=app, error=str(exc))
            return ToolResult.fail(error=str(exc), execution_time_ms=elapsed)
