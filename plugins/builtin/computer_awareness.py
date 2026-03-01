"""Computer awareness tools — gives Emily full knowledge of the host system.

Covers:
  - computer_search   : find files/folders by name, glob, or text content
  - list_apps         : enumerate every installed desktop application
  - system_info       : full hardware + OS + GPU + disk + network snapshot
  - list_windows      : open windows and their titles (via wmctrl / xdotool)
  - clipboard_tool    : read and write the system clipboard
  - recent_files      : recently opened files from ~/.local/share/recently-used.xbel
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import psutil

from observability.logger import get_logger
from plugins.base import BaseTool, ExecutionContext, ToolResult, ValidationResult

log = get_logger(__name__)

_DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
    Path("/snap/bin"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _parse_desktop_file(path: Path) -> dict[str, str]:
    """Extract Name, Exec, Comment, Categories from a .desktop file."""
    info: dict[str, str] = {"path": str(path)}
    try:
        for line in path.read_text(errors="replace").splitlines():
            for key in ("Name", "Exec", "Comment", "Categories", "Icon"):
                if line.startswith(f"{key}="):
                    info[key.lower()] = line[len(key) + 1 :].strip()
    except OSError:
        pass
    return info


async def _run(cmd: list[str], timeout: float = 5.0) -> tuple[int, str, str]:
    """Run a subprocess, return (returncode, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (
            proc.returncode or 0,
            stdout.decode(errors="replace"),
            stderr.decode(errors="replace"),
        )
    except TimeoutError:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Computer Search
# ─────────────────────────────────────────────────────────────────────────────


class ComputerSearchTool(BaseTool):
    """Search the filesystem for files, folders, or content."""

    name = "computer_search"
    description = (
        "Search the computer for files, folders, or text content. "
        "Find files by name or glob pattern, or search inside files for text. "
        "Examples: find all PDFs in home, find a file called 'resume.docx', "
        "search all Python files for a function name."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Filename, glob pattern (*.pdf), or text to search for inside files.",
            },
            "search_in": {
                "type": "string",
                "description": "Directory to search in. Default: user's home directory.",
                "default": "~",
            },
            "mode": {
                "type": "string",
                "enum": ["name", "content", "both"],
                "description": "'name' = find files/folders by name/glob, 'content' = grep inside files, 'both' = try both. Default: name.",
                "default": "name",
            },
            "file_type": {
                "type": "string",
                "enum": ["any", "file", "dir"],
                "description": "Filter by type. Default: any.",
                "default": "any",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return. Default: 50.",
                "default": 50,
            },
        },
        "required": ["query"],
    }
    requires_approval = False
    timeout_seconds = 20

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will search for: {params.get('query')} in {params.get('search_in', '~')}"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        if not params.get("query", "").strip():
            return ValidationResult.fail("query is required")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        query = params["query"].strip()
        root = str(Path(params.get("search_in", "~")).expanduser().resolve())
        mode = params.get("mode", "name")
        file_type = params.get("file_type", "any")
        max_results = int(params.get("max_results", 50))
        t0 = time.monotonic()

        results: list[dict] = []

        # ── Name / glob search via `find` ──────────────────────────────────
        if mode in ("name", "both"):
            type_flag = []
            if file_type == "file":
                type_flag = ["-type", "f"]
            elif file_type == "dir":
                type_flag = ["-type", "d"]

            # Decide if query looks like a glob or a plain name
            if any(c in query for c in ("*", "?", "[")):
                name_flag = ["-name", query]
            else:
                name_flag = ["-iname", f"*{query}*"]

            find_cmd = ["find", root, *type_flag, *name_flag, "-not", "-path", "*/.git/*"]
            rc, stdout, _ = await _run(find_cmd, timeout=15.0)
            for line in stdout.splitlines():
                if line.strip():
                    p = Path(line.strip())
                    results.append(
                        {
                            "path": str(p),
                            "name": p.name,
                            "type": "dir" if p.is_dir() else "file",
                            "match": "name",
                        }
                    )
                if len(results) >= max_results:
                    break

        # ── Content search via ripgrep (preferred) or grep ─────────────────
        if mode in ("content", "both") and len(results) < max_results:
            if shutil.which("rg"):
                content_cmd = ["rg", "--files-with-matches", "--no-messages", "-i", query, root]
            elif shutil.which("grep"):
                content_cmd = ["grep", "-rl", "-i", query, root]
            else:
                content_cmd = []

            if content_cmd:
                rc, stdout, _ = await _run(content_cmd, timeout=15.0)
                seen = {r["path"] for r in results}
                for line in stdout.splitlines():
                    if line.strip() and line not in seen:
                        p = Path(line.strip())
                        results.append(
                            {
                                "path": str(p),
                                "name": p.name,
                                "type": "file",
                                "match": "content",
                            }
                        )
                        seen.add(line)
                    if len(results) >= max_results:
                        break

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=results,
            execution_time_ms=elapsed,
            count=len(results),
            query=query,
            root=root,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. List Installed Apps
# ─────────────────────────────────────────────────────────────────────────────


class ListAppsTool(BaseTool):
    """Enumerate every installed desktop application."""

    name = "list_apps"
    description = (
        "List all installed applications on the computer. "
        "Returns app names, their launch commands, categories, and descriptions. "
        "Use this to discover what software is available before launching something."
    )
    parameters = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Optional text filter — only return apps whose name or category matches.",
            },
            "include_path": {
                "type": "boolean",
                "description": "Include PATH binaries in addition to .desktop apps. Default: false.",
                "default": False,
            },
        },
    }
    requires_approval = False
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Will list all installed applications"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        flt = params.get("filter", "").lower().strip()
        include_path = params.get("include_path", False)
        t0 = time.monotonic()

        apps: list[dict] = []
        seen_names: set[str] = set()

        for desktop_dir in _DESKTOP_DIRS:
            if not desktop_dir.exists():
                continue
            for desktop in sorted(desktop_dir.glob("*.desktop")):
                info = _parse_desktop_file(desktop)
                name = info.get("name", desktop.stem)
                if name in seen_names:
                    continue
                seen_names.add(name)
                # Skip hidden/nodisplay apps unless filter explicitly matches
                if not info.get("name"):
                    continue
                if (
                    flt
                    and flt not in name.lower()
                    and flt not in info.get("categories", "").lower()
                ):
                    continue
                apps.append(
                    {
                        "name": name,
                        "exec": info.get("exec", ""),
                        "comment": info.get("comment", ""),
                        "categories": info.get("categories", ""),
                        "source": "desktop",
                        "desktop_file": str(desktop),
                    }
                )

        if include_path:
            rc, stdout, _ = await _run(["bash", "-lc", "compgen -c"], timeout=5.0)
            path_bins = sorted(set(stdout.splitlines()))
            for b in path_bins:
                if b and b not in seen_names and (not flt or flt in b.lower()):
                    seen_names.add(b)
                    apps.append({"name": b, "source": "PATH"})

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(
            output=apps,
            execution_time_ms=elapsed,
            count=len(apps),
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. System Info
# ─────────────────────────────────────────────────────────────────────────────


class SystemInfoTool(BaseTool):
    """Full system snapshot — hardware, OS, memory, disks, GPU, network."""

    name = "system_info"
    description = (
        "Get a full snapshot of the computer's current state: "
        "CPU model and usage, RAM, disk space, GPU info (NVIDIA), "
        "OS version, hostname, uptime, network interfaces, and top processes. "
        "Use this to understand the machine Emily is running on."
    )
    parameters = {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Which sections to include. Default: all. Options: cpu, memory, disk, gpu, os, network, processes.",
            },
        },
    }
    requires_approval = False
    timeout_seconds = 10

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Will gather full system information"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        want = set(params.get("sections", [])) or {
            "cpu",
            "memory",
            "disk",
            "gpu",
            "os",
            "network",
            "processes",
        }
        t0 = time.monotonic()
        info: dict[str, Any] = {}

        if "os" in want:
            boot_time = psutil.boot_time()
            uptime_s = time.time() - boot_time
            info["os"] = {
                "hostname": platform.node(),
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "python": platform.python_version(),
                "uptime_hours": round(uptime_s / 3600, 1),
            }
            # Try to get distro name
            try:
                with open("/etc/os-release") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            info["os"]["distro"] = line.split("=", 1)[1].strip().strip('"')
                            break
            except OSError:
                pass

        if "cpu" in want:
            freq = psutil.cpu_freq()
            info["cpu"] = {
                "model": platform.processor() or "unknown",
                "physical_cores": psutil.cpu_count(logical=False),
                "logical_cores": psutil.cpu_count(logical=True),
                "usage_percent": psutil.cpu_percent(interval=0.3),
                "freq_mhz": round(freq.current, 0) if freq else None,
                "freq_max_mhz": round(freq.max, 0) if freq else None,
            }

        if "memory" in want:
            vm = psutil.virtual_memory()
            swap = psutil.swap_memory()
            info["memory"] = {
                "total_gb": round(vm.total / 1e9, 2),
                "available_gb": round(vm.available / 1e9, 2),
                "used_gb": round(vm.used / 1e9, 2),
                "percent": vm.percent,
                "swap_total_gb": round(swap.total / 1e9, 2),
                "swap_used_gb": round(swap.used / 1e9, 2),
            }

        if "disk" in want:
            disks = []
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append(
                        {
                            "device": part.device,
                            "mountpoint": part.mountpoint,
                            "fstype": part.fstype,
                            "total_gb": round(usage.total / 1e9, 2),
                            "used_gb": round(usage.used / 1e9, 2),
                            "free_gb": round(usage.free / 1e9, 2),
                            "percent": usage.percent,
                        }
                    )
                except PermissionError:
                    pass
            info["disk"] = disks

        if "gpu" in want:
            gpus = []
            if shutil.which("nvidia-smi"):
                rc, stdout, _ = await _run(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,driver_version",
                        "--format=csv,noheader,nounits",
                    ],
                    timeout=5.0,
                )
                for line in stdout.strip().splitlines():
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 6:
                        gpus.append(
                            {
                                "name": parts[0],
                                "temp_c": parts[1],
                                "utilization_pct": parts[2],
                                "memory_used_mb": parts[3],
                                "memory_total_mb": parts[4],
                                "driver": parts[5],
                            }
                        )
            info["gpu"] = gpus

        if "network" in want:
            ifaces = []
            for name, addrs in psutil.net_if_addrs().items():
                iface: dict[str, Any] = {"name": name, "addresses": []}
                for addr in addrs:
                    iface["addresses"].append(
                        {
                            "family": str(addr.family).replace("AddressFamily.", ""),
                            "address": addr.address,
                        }
                    )
                ifaces.append(iface)
            info["network"] = ifaces

        if "processes" in want:
            procs = []
            for p in sorted(
                psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]),
                key=lambda p: -(p.info.get("cpu_percent") or 0),
            )[:15]:
                procs.append(
                    {
                        "pid": p.info["pid"],
                        "name": p.info["name"],
                        "cpu_pct": round(p.info.get("cpu_percent") or 0, 1),
                        "mem_pct": round(p.info.get("memory_percent") or 0, 2),
                    }
                )
            info["processes"] = procs

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(output=info, execution_time_ms=elapsed)


# ─────────────────────────────────────────────────────────────────────────────
# 4. List Open Windows
# ─────────────────────────────────────────────────────────────────────────────


class ListWindowsTool(BaseTool):
    """List all currently open windows and which app owns them."""

    name = "list_windows"
    description = (
        "List all currently open windows on the desktop — app names, window titles, "
        "and window IDs. Useful for knowing what the user has open right now. "
        "Requires wmctrl or xdotool to be installed."
    )
    parameters = {
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Optional text filter on window title or app name.",
            },
        },
    }
    requires_approval = False
    timeout_seconds = 5

    async def dry_run(self, params: dict[str, Any]) -> str:
        return "Will list open windows"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        if not shutil.which("wmctrl") and not shutil.which("xdotool"):
            return ValidationResult.fail("Neither wmctrl nor xdotool is installed")
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        flt = params.get("filter", "").lower().strip()
        t0 = time.monotonic()
        windows: list[dict] = []

        if shutil.which("wmctrl"):
            rc, stdout, _ = await _run(["wmctrl", "-l", "-x"], timeout=4.0)
            for line in stdout.splitlines():
                parts = line.split(None, 4)
                if len(parts) >= 5:
                    win = {
                        "id": parts[0],
                        "desktop": parts[1],
                        "app_class": parts[2],
                        "host": parts[3],
                        "title": parts[4],
                    }
                    if not flt or flt in win["title"].lower() or flt in win["app_class"].lower():
                        windows.append(win)
        elif shutil.which("xdotool"):
            rc, stdout, _ = await _run(
                ["xdotool", "search", "--onlyvisible", "--name", flt or ""], timeout=4.0
            )
            for wid in stdout.splitlines():
                wid = wid.strip()
                if wid:
                    _, name, _ = await _run(["xdotool", "getwindowname", wid], timeout=2.0)
                    windows.append({"id": wid, "title": name.strip()})

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(output=windows, execution_time_ms=elapsed, count=len(windows))


# ─────────────────────────────────────────────────────────────────────────────
# 5. Clipboard
# ─────────────────────────────────────────────────────────────────────────────


class ClipboardTool(BaseTool):
    """Read from or write to the system clipboard."""

    name = "clipboard"
    description = (
        "Read what's currently in the clipboard, or write new content to it. "
        "Supports Wayland (wl-clipboard) and X11 (xclip / xsel)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write"],
                "description": "'read' returns clipboard contents; 'write' sets them.",
            },
            "text": {
                "type": "string",
                "description": "Text to write to clipboard. Required when action='write'.",
            },
        },
        "required": ["action"],
    }
    requires_approval = False
    timeout_seconds = 5

    def _get_paste_cmd(self) -> list[str] | None:
        if shutil.which("wl-paste"):
            return ["wl-paste", "--no-newline"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-out"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--output"]
        return None

    def _get_copy_cmd(self) -> list[str] | None:
        if shutil.which("wl-copy"):
            return ["wl-copy"]
        if shutil.which("xclip"):
            return ["xclip", "-selection", "clipboard", "-in"]
        if shutil.which("xsel"):
            return ["xsel", "--clipboard", "--input"]
        return None

    async def dry_run(self, params: dict[str, Any]) -> str:
        action = params.get("action", "read")
        if action == "write":
            preview = (params.get("text", "") or "")[:40]
            return f"Will write to clipboard: {preview!r}..."
        return "Will read clipboard contents"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        action = params.get("action", "read")
        if action == "write":
            if not params.get("text"):
                return ValidationResult.fail("text is required for write action")
            if not self._get_copy_cmd():
                return ValidationResult.fail(
                    "No clipboard write tool found (wl-copy / xclip / xsel)"
                )
        else:
            if not self._get_paste_cmd():
                return ValidationResult.fail(
                    "No clipboard read tool found (wl-paste / xclip / xsel)"
                )
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        action = params.get("action", "read")
        t0 = time.monotonic()

        if action == "read":
            cmd = self._get_paste_cmd()
            rc, stdout, stderr = await _run(cmd, timeout=4.0)
            elapsed = (time.monotonic() - t0) * 1000
            if rc == 0:
                return ToolResult.ok(output=stdout, execution_time_ms=elapsed, length=len(stdout))
            return ToolResult.fail(
                error=stderr.strip() or "Failed to read clipboard", execution_time_ms=elapsed
            )

        else:  # write
            text = params.get("text", "")
            cmd = self._get_copy_cmd()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(
                    proc.communicate(input=text.encode()), timeout=4.0
                )
                elapsed = (time.monotonic() - t0) * 1000
                if proc.returncode == 0:
                    return ToolResult.ok(
                        output="Clipboard updated", execution_time_ms=elapsed, length=len(text)
                    )
                return ToolResult.fail(
                    error=stderr.decode(errors="replace").strip(), execution_time_ms=elapsed
                )
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                return ToolResult.fail(error=str(exc), execution_time_ms=elapsed)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Recent Files
# ─────────────────────────────────────────────────────────────────────────────


class RecentFilesTool(BaseTool):
    """List the files the user has recently opened."""

    name = "recent_files"
    description = (
        "List recently opened files from the system's recent files log "
        "(~/.local/share/recently-used.xbel). Shows what the user has been working on."
    )
    parameters = {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Number of recent files to return. Default: 20.",
                "default": 20,
            },
            "filter": {
                "type": "string",
                "description": "Optional text filter on filename or MIME type.",
            },
        },
    }
    requires_approval = False
    timeout_seconds = 5

    _XBEL = Path.home() / ".local/share/recently-used.xbel"

    async def dry_run(self, params: dict[str, Any]) -> str:
        return f"Will list {params.get('limit', 20)} recently opened files"

    async def validate(self, params: dict[str, Any]) -> ValidationResult:
        if not self._XBEL.exists():
            return ValidationResult.fail(
                "recently-used.xbel not found — recent files log unavailable"
            )
        return ValidationResult.ok()

    async def execute(self, params: dict[str, Any], context: ExecutionContext) -> ToolResult:
        limit = int(params.get("limit", 20))
        flt = params.get("filter", "").lower().strip()
        t0 = time.monotonic()

        try:
            tree = ET.parse(self._XBEL)
            root = tree.getroot()
        except ET.ParseError as exc:
            elapsed = (time.monotonic() - t0) * 1000
            return ToolResult.fail(
                error=f"Failed to parse recent files: {exc}", execution_time_ms=elapsed
            )

        ns = {"xbel": "http://www.freedesktop.org/standards/recently-used"}
        bookmarks = root.findall("bookmark") or root.findall("xbel:bookmark", ns)

        files: list[dict] = []
        for bm in reversed(bookmarks):  # most recent last in file
            href = bm.get("href", "")
            modified = bm.get("modified", bm.get("visited", ""))
            mime = ""
            for info in bm.findall("info") or bm.findall("xbel:info", ns):
                for meta in info.findall("metadata") or info.findall("xbel:metadata", ns):
                    for child in meta:
                        if "mime-type" in child.tag:
                            mime = child.get("type", "")

            path = href.replace("file://", "")
            name = Path(path).name if path else href
            if flt and flt not in name.lower() and flt not in mime.lower():
                continue
            files.append(
                {
                    "name": name,
                    "path": path,
                    "href": href,
                    "modified": modified,
                    "mime_type": mime,
                }
            )
            if len(files) >= limit:
                break

        elapsed = (time.monotonic() - t0) * 1000
        return ToolResult.ok(output=files, execution_time_ms=elapsed, count=len(files))
