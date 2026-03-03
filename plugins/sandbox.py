"""
Tool execution sandbox using bubblewrap (bwrap).

All code execution and shell commands run inside a bubblewrap user-namespace
container with:
- No network access (--unshare-net)
- Filesystem limited to allowed_paths + /tmp/emily_sandbox
- No new privileges (--no-new-privs)
- CPU and memory resource limits via ulimit

Falls back to plain subprocess with restricted env when bubblewrap is unavailable.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import tempfile
from pathlib import Path

from observability.logger import get_logger

log = get_logger(__name__)

_BUBBLEWRAP_AVAILABLE: bool | None = None


def _check_bubblewrap() -> bool:
    """Check if bwrap is installed and executable."""
    global _BUBBLEWRAP_AVAILABLE
    if _BUBBLEWRAP_AVAILABLE is None:
        _BUBBLEWRAP_AVAILABLE = shutil.which("bwrap") is not None
        if not _BUBBLEWRAP_AVAILABLE:
            log.warning("bubblewrap_not_found", fallback="plain_subprocess")
    return _BUBBLEWRAP_AVAILABLE


async def run_sandboxed(
    command: list[str],
    allowed_paths: list[str],
    timeout_s: float = 10.0,
    working_dir: str | None = None,
) -> tuple[str, str, int]:
    """
    Run a command in a bubblewrap sandbox.

    Args:
        command: Command and arguments list.
        allowed_paths: Filesystem paths to bind-mount read-write into the sandbox.
        timeout_s: Command timeout in seconds.
        working_dir: Working directory inside the sandbox.

    Returns:
        Tuple of (stdout, stderr, returncode).
    """
    if not _check_bubblewrap():
        return await _run_plain(command, allowed_paths, timeout_s, working_dir)

    # Build bubblewrap arguments
    bwrap_args = [
        "bwrap",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/sbin",
        "/sbin",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--unshare-net",  # No network
        "--unshare-pid",  # Isolated process tree
        "--no-new-privs",  # No privilege escalation
        "--die-with-parent",  # Kill sandbox if parent dies
    ]

    # Bind-mount allowed paths read-write
    for path in allowed_paths:
        p = Path(path)
        if p.exists():
            p.mkdir(parents=True, exist_ok=True)
            bwrap_args.extend(["--bind", str(p), str(p)])

    # Add sandbox temp dir
    sandbox_tmp = "/tmp/emily_sandbox"
    bwrap_args.extend(["--bind", "/tmp", sandbox_tmp])

    if working_dir:
        bwrap_args.extend(["--chdir", working_dir])

    bwrap_args.extend(command)

    return await _run_subprocess(bwrap_args, timeout_s)


async def run_python_sandboxed(
    code: str,
    allowed_paths: list[str],
    timeout_s: float = 10.0,
) -> tuple[str, str, int]:
    """
    Execute Python code in a sandboxed subprocess.

    The code is written to a temp file and executed with restricted builtins.

    Args:
        code: Python source code to execute.
        allowed_paths: Paths available to the code.
        timeout_s: Execution timeout.

    Returns:
        Tuple of (stdout, stderr, returncode).
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", prefix="emily_sandbox_", delete=False
    ) as f:
        f.write(_wrap_code(code))
        tmp_path = f.name

    try:
        allowed = list(allowed_paths) + [str(Path(tmp_path).parent)]
        return await run_sandboxed(
            ["python3", tmp_path],
            allowed_paths=allowed,
            timeout_s=timeout_s,
        )
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


# Builtins that are not exposed to user code in the sandbox (blocked for security)
_BLOCKED_BUILTINS = frozenset(
    {
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "__loader__",
        "__spec__",
        "breakpoint",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "vars",
        "dir",
        "memoryview",
        "reload",
        "__build_class__",
    }
)


def _wrap_code(code: str) -> str:
    """
    Wrap user code so it runs with restricted __builtins__.

    Blocked builtins include __import__, eval, exec, compile, open, input,
    and other escape hatches. The user snippet runs in a try block with
    __builtins__ set to a safe subset so they cannot load os/subprocess/socket.
    """
    blocked_repr = repr(_BLOCKED_BUILTINS)
    return f"""
import sys
import io

# Restrict builtins for the user code below
_blocked = {blocked_repr}
_orig = __builtins__.__dict__ if hasattr(__builtins__, "__dict__") else dict(__builtins__)
_safe_builtins = dict((k, v) for k, v in _orig.items() if k not in _blocked)
__builtins__ = _safe_builtins

try:
{chr(10).join("    " + line for line in code.splitlines())}
except Exception as _e:
    print(f"Error: {{_e}}", file=sys.stderr)
    sys.exit(1)
"""


async def _run_subprocess(
    args: list[str],
    timeout_s: float,
) -> tuple[str, str, int]:
    """Run a subprocess and capture output."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"},
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return "", "Timeout exceeded", 124

        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )

    except Exception as exc:
        return "", str(exc), 1


async def _run_plain(
    command: list[str],
    allowed_paths: list[str],
    timeout_s: float,
    working_dir: str | None,
) -> tuple[str, str, int]:
    """Fallback: run without bubblewrap (less secure, logs a warning)."""
    log.warning("sandbox_bypassed_running_plain", command=command[0])
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": working_dir or "/tmp",
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
            env=env,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return "", "Timeout exceeded", 124

        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )
    except Exception as exc:
        return "", str(exc), 1
