"""
Emily Terminal Commands — command registry and implementations.
"""

from __future__ import annotations

import asyncio
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    from observability.logger import get_logger

    log = get_logger(__name__)
except ImportError:
    import logging

    log = logging.getLogger(__name__)

from .help_system import help_system

API_BASE = "http://localhost:8001"
EMILY_ROOT = Path(__file__).parent.parent.parent


# ── Result type ──────────────────────────────────────────────────────────────


class CommandResult:
    def __init__(self, success: bool, message: str, data: dict[str, Any] | None = None):
        self.success = success
        self.message = message
        self.data = data or {}
        self.timestamp = datetime.now()


# ── Registry ─────────────────────────────────────────────────────────────────


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, Callable] = {}
        self._aliases: dict[str, str] = {}

    def register(self, name: str, aliases: list[str] | None = None):
        def decorator(func: Callable) -> Callable:
            self._commands[name] = func
            for alias in aliases or []:
                self._aliases[alias] = name
            return func

        return decorator

    def get_command(self, name: str) -> Callable | None:
        return self._commands.get(self._aliases.get(name, name))

    def list_commands(self) -> list[str]:
        return list(self._commands.keys())

    def list_all_names(self) -> list[str]:
        return list(self._commands.keys()) + list(self._aliases.keys())


registry = CommandRegistry()


# ── Application manager ───────────────────────────────────────────────────────


class ApplicationManager:
    def __init__(self) -> None:
        self._running: dict[str, subprocess.Popen] = {}

    def _cmd(self, app: str) -> str | None:
        return {
            "api": "uv run uvicorn api.app:app --host 127.0.0.1 --port 8001 --reload",
            "web": "cd web && npm run dev",
            "core": "uv run python main.py --no-gui",
            "desktop": "uv run python -m ui.desktop",
            "terminal": "uv run python -m ui.terminal.app",
        }.get(app)

    async def start(self, app: str) -> CommandResult:
        cmd = self._cmd(app)
        if not cmd:
            return CommandResult(False, f"Unknown app '{app}'. Try: api web core desktop terminal")
        if app in self._running:
            return CommandResult(False, f"{app} is already running")
        try:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                cwd=EMILY_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self._running[app] = proc
            await asyncio.sleep(1)
            if proc.poll() is None:
                return CommandResult(True, f"Started {app} (PID {proc.pid})")
            _, stderr = proc.communicate()
            del self._running[app]
            return CommandResult(False, f"Failed: {(stderr or '').strip()[:200]}")
        except Exception as exc:
            return CommandResult(False, str(exc))

    async def stop(self, app: str) -> CommandResult:
        if app not in self._running:
            return CommandResult(False, f"{app} is not running")
        proc = self._running[app]
        proc.terminate()
        await asyncio.sleep(2)
        if proc.poll() is None:
            proc.kill()
        del self._running[app]
        return CommandResult(True, f"Stopped {app}")

    async def restart(self, app: str) -> CommandResult:
        if app in self._running:
            res = await self.stop(app)
            if not res.success:
                return res
        await asyncio.sleep(1)
        return await self.start(app)

    def status(self) -> dict[str, Any]:
        out = {}
        for app, proc in self._running.items():
            out[app] = {"running": proc.poll() is None, "pid": proc.pid}
        return out


app_manager = ApplicationManager()


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _api_get(path: str) -> tuple[bool, Any]:
    """GET from Emily API. Returns (ok, json_or_error_str)."""
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{API_BASE}{path}")
            if r.is_success:
                return True, r.json()
            return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, str(exc)


async def _api_post(path: str, body: dict | None = None) -> tuple[bool, Any]:
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{API_BASE}{path}", json=body or {})
            if r.is_success:
                return True, r.json()
            return False, f"HTTP {r.status_code}"
    except Exception as exc:
        return False, str(exc)


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ── Commands ─────────────────────────────────────────────────────────────────


@registry.register("help", aliases=["h", "?"])
async def cmd_help(args: list[str]) -> CommandResult:
    """Show help information."""
    if not args:
        return CommandResult(True, help_system.get_help())
    topic = args[0].lower()
    if topic == "apps":
        return CommandResult(True, help_system.get_apps_help())
    if topic == "commands":
        return CommandResult(True, help_system.get_commands_help())
    return CommandResult(True, help_system.get_help(topic))


@registry.register("start", aliases=["run", "launch"])
async def cmd_start(args: list[str]) -> CommandResult:
    """Start an Emily application (api | web | core | desktop | terminal | all)."""
    if not args:
        return CommandResult(
            False, "Usage: /start <app>  —  api | web | core | desktop | terminal | all"
        )
    app = args[0].lower()
    if app == "all":
        lines = []
        for name in ("api", "core"):
            r = await app_manager.start(name)
            lines.append(f"{'✓' if r.success else '✗'} {r.message}")
        return CommandResult(True, "Starting Emily stack:\n" + "\n".join(lines))
    return await app_manager.start(app)


@registry.register("stop", aliases=["kill", "terminate"])
async def cmd_stop(args: list[str]) -> CommandResult:
    """Stop a running application."""
    if not args:
        return CommandResult(False, "Usage: /stop <app>")
    return await app_manager.stop(args[0].lower())


@registry.register("restart", aliases=["reload", "reboot"])
async def cmd_restart(args: list[str]) -> CommandResult:
    """Restart an application."""
    if not args:
        return CommandResult(False, "Usage: /restart <app>")
    return await app_manager.restart(args[0].lower())


@registry.register("status", aliases=["ps", "list"])
async def cmd_status(args: list[str]) -> CommandResult:
    """Show status of managed applications."""
    s = app_manager.status()
    if not s:
        return CommandResult(True, "No managed applications running\n(Use /start to launch one)")
    lines = ["Managed Applications:"]
    for app, info in s.items():
        sym = "✓" if info["running"] else "✗"
        pid = f" PID {info['pid']}" if info["running"] else " stopped"
        lines.append(f"  {sym} {app:<12}{pid}")
    return CommandResult(True, "\n".join(lines))


@registry.register("health", aliases=["check", "ping"])
async def cmd_health(args: list[str]) -> CommandResult:
    """Check Emily API health and service status."""
    lines = ["Emily System Health"]
    lines.append("─" * 30)

    # API ping
    ok, data = await _api_get("/api/settings/auth/status")
    if ok:
        lines.append(f"  ✓ API  reachable at {API_BASE}")
    else:
        lines.append(f"  ✗ API  unreachable — {data}")

    # Voice status
    ok2, voice = await _api_get("/api/audio/voice/status")
    if ok2:
        state = voice.get("state", "unknown")
        active = voice.get("active", False)
        sym = "◉" if active else "○"
        lines.append(f"  {sym} Voice  {state}")
    else:
        lines.append("  ✗ Voice status unavailable")

    # Managed apps
    s = app_manager.status()
    lines.append("")
    lines.append("Managed processes:")
    if s:
        for app, info in s.items():
            sym = "✓" if info["running"] else "✗"
            lines.append(f"  {sym} {app}")
    else:
        lines.append("  (none started from this terminal)")

    return CommandResult(True, "\n".join(lines))


@registry.register("model", aliases=["models", "tier"])
async def cmd_model(args: list[str]) -> CommandResult:
    """Show or query Emily model configuration."""
    try:
        from config import get_settings

        s = get_settings()
        m = s.llm.models
        tb = s.llm.tier_backend

        lines = ["LLM Model Fleet", "─" * 46]
        tiers = [
            ("nano", m.nano, tb.nano),
            ("voice_fast", m.voice_fast, tb.voice_fast),
            ("fast", m.fast, tb.fast),
            ("smart", m.smart, tb.smart),
            ("reasoning", m.reasoning, tb.reasoning),
            ("vision", m.vision, tb.vision),
            ("embedding", m.embedding, tb.embedding),
        ]
        for tier, model, backend in tiers:
            short = model.split("/")[-1] if "/" in model else model
            lines.append(f"  {tier:<12} {backend:<10} {short}")
        return CommandResult(True, "\n".join(lines))
    except Exception as exc:
        return CommandResult(False, f"Cannot read config: {exc}")


@registry.register("gpu", aliases=["vram", "nvidia"])
async def cmd_gpu(args: list[str]) -> CommandResult:
    """Show GPU and VRAM usage."""
    # Try nvidia-smi first
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            lines = ["GPU Status", "─" * 40]
            for i, row in enumerate(result.stdout.strip().split("\n")):
                parts = [p.strip() for p in row.split(",")]
                if len(parts) >= 5:
                    name, temp, util, used, total = parts[:5]
                    used_gb = int(used) / 1024
                    total_gb = int(total) / 1024
                    bar_used = int(used_gb / total_gb * 20)
                    bar = "█" * bar_used + "░" * (20 - bar_used)
                    lines.append(f"  GPU {i}: {name}")
                    lines.append(f"  Temp: {temp}°C  Util: {util}%")
                    lines.append(f"  VRAM: [{bar}] {used_gb:.1f}/{total_gb:.1f} GB")
                    lines.append("")
            return CommandResult(True, "\n".join(lines).rstrip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: gputil
    try:
        import GPUtil

        gpus = GPUtil.getGPUs()
        if not gpus:
            return CommandResult(False, "No NVIDIA GPU detected")
        lines = ["GPU Status", "─" * 40]
        for gpu in gpus:
            used_gb = gpu.memoryUsed / 1024
            total_gb = gpu.memoryTotal / 1024
            bar_used = int(gpu.memoryUtil * 20)
            bar = "█" * bar_used + "░" * (20 - bar_used)
            lines.append(f"  {gpu.name}")
            lines.append(f"  Temp: {gpu.temperature}°C  Util: {gpu.load * 100:.0f}%")
            lines.append(f"  VRAM: [{bar}] {used_gb:.1f}/{total_gb:.1f} GB")
        return CommandResult(True, "\n".join(lines))
    except ImportError:
        pass

    return CommandResult(False, "nvidia-smi not found — install NVIDIA drivers or GPUtil")


@registry.register("metrics", aliases=["stats", "sys"])
async def cmd_metrics(args: list[str]) -> CommandResult:
    """Show CPU, RAM, and disk usage."""
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        lines = [
            "System Metrics",
            "─" * 30,
            f"  CPU:   {cpu:.1f}%",
            f"  RAM:   {mem.percent:.1f}%  ({mem.used // 1024 // 1024} / {mem.total // 1024 // 1024} MB)",
            f"  Disk:  {disk.percent:.1f}%  ({disk.used // 1024**3} / {disk.total // 1024**3} GB)",
        ]
        return CommandResult(True, "\n".join(lines))
    except ImportError:
        return CommandResult(False, "psutil not available")


@registry.register("logs", aliases=["log"])
async def cmd_logs(args: list[str]) -> CommandResult:
    """Show recent log entries from Emily's log directory."""
    logs_dir = EMILY_ROOT / "logs"
    lines_count = 30
    if len(args) > 1 and args[1].isdigit():
        lines_count = int(args[1])

    # Find the most recent log file, or a named one
    if args and not args[0].isdigit():
        target = args[0]
        candidates = list(logs_dir.glob(f"*{target}*"))
    else:
        candidates = sorted(logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not candidates:
        return CommandResult(
            False,
            f"No log files in {logs_dir}\nLog files are created when Emily runs.",
        )

    log_file = candidates[0]
    try:
        text = log_file.read_text(errors="replace")
        log_lines = text.strip().split("\n")
        recent = log_lines[-lines_count:]
        header = f"── {log_file.name} (last {len(recent)} lines) ──"
        return CommandResult(True, header + "\n" + "\n".join(recent))
    except Exception as exc:
        return CommandResult(False, f"Cannot read {log_file}: {exc}")


@registry.register("conv", aliases=["conversation", "convs"])
async def cmd_conv(args: list[str]) -> CommandResult:
    """List or manage conversations  (list | new | <id>)."""
    sub = args[0].lower() if args else "list"

    if sub in ("list", "ls"):
        ok, data = await _api_get("/api/conversations")
        if not ok:
            return CommandResult(False, f"Cannot reach API: {data}")
        convs = data.get("conversations", data) if isinstance(data, dict) else data
        if not convs:
            return CommandResult(True, "No conversations yet")
        lines = ["Conversations:", "─" * 50]
        for c in convs[:20]:
            cid = c.get("id", "?")[:8]
            title = c.get("title", "Untitled")[:35]
            msgs = c.get("total_messages", 0)
            lines.append(f"  {cid}  {title:<35} {msgs}msg")
        return CommandResult(True, "\n".join(lines))

    if sub == "new":
        return CommandResult(True, "NEW_CONVERSATION")

    return CommandResult(False, f"Unknown subcommand '{sub}'. Try: /conv list | /conv new")


@registry.register("new", aliases=["newconv", "reset"])
async def cmd_new(args: list[str]) -> CommandResult:
    """Start a new conversation (clears context)."""
    return CommandResult(True, "NEW_CONVERSATION")


@registry.register("voice", aliases=["mic", "listen"])
async def cmd_voice(args: list[str]) -> CommandResult:
    """Start or stop voice mode  (/voice start | /voice stop | /voice status)."""
    sub = args[0].lower() if args else "status"

    ok, data = await _api_get("/api/audio/voice/status")
    if not ok:
        return CommandResult(False, f"Voice API unavailable: {data}")

    active = data.get("active", False)
    state = data.get("state", "unknown")

    if sub == "status":
        lines = ["Voice Status", "─" * 30]
        lines.append(f"  Active:  {'yes' if active else 'no'}")
        lines.append(f"  State:   {state}")
        for key in ("stt_model", "llm_model", "tts_voice"):
            val = data.get(key)
            if val:
                lines.append(f"  {key:<10} {val}")
        return CommandResult(True, "\n".join(lines))

    if sub in ("start", "on"):
        if active:
            return CommandResult(True, "Voice mode is already active")
        ok2, _ = await _api_post("/api/audio/voice/start")
        return CommandResult(ok2, "Voice mode started — speak!" if ok2 else "Failed to start voice")

    if sub in ("stop", "off"):
        if not active:
            return CommandResult(True, "Voice mode is not active")
        ok2, _ = await _api_post("/api/audio/voice/stop")
        return CommandResult(ok2, "Voice mode stopped" if ok2 else "Failed to stop voice")

    return CommandResult(False, "Usage: /voice [start | stop | status]")


@registry.register("profile", aliases=["who", "owner"])
async def cmd_profile(args: list[str]) -> CommandResult:
    """Show current owner profile."""
    ok, data = await _api_get("/api/settings/profile")
    if not ok:
        return CommandResult(False, f"Cannot reach API: {data}")
    lines = [
        "Owner Profile",
        "─" * 30,
        f"  Name:    {data.get('name', '?')}",
        f"  AI name: {data.get('ai_name', 'Emily')}",
        f"  Email:   {data.get('email', '(not set)')}",
    ]
    return CommandResult(True, "\n".join(lines))


@registry.register("persona", aliases=["personality"])
async def cmd_persona(args: list[str]) -> CommandResult:
    """Show or set personality traits  (/persona  or  /persona warmth 0.8)."""
    if len(args) >= 2:
        trait, value = args[0].lower(), args[1]
        try:
            ok, data = await _api_post(  # type: ignore[assignment]
                "/api/settings/persona", {trait: float(value)}
            )
        except ValueError:
            return CommandResult(False, "Value must be 0.0–1.0")
        if not ok:
            return CommandResult(False, str(data))
        return CommandResult(True, f"Set {trait} = {value}")

    ok, data = await _api_get("/api/settings/persona")
    if not ok:
        return CommandResult(False, str(data))
    lines = ["Personality Traits", "─" * 30]
    for trait, val in data.items():
        bar = "█" * int(float(val) * 20) + "░" * (20 - int(float(val) * 20))
        lines.append(f"  {trait:<12} [{bar}] {float(val):.2f}")
    lines.append("")
    lines.append("Change: /persona <trait> <0.0–1.0>")
    return CommandResult(True, "\n".join(lines))


@registry.register("clear", aliases=["cls", "clean"])
async def cmd_clear(args: list[str]) -> CommandResult:
    """Clear the conversation panel."""
    return CommandResult(True, "CLEAR_SCREEN")


@registry.register("browser", aliases=["browse", "web", "w3m"])
async def cmd_browser(args: list[str]) -> CommandResult:
    """Launch w3m terminal browser  (/browser <url>  or  /browser google <query>)."""
    if not args:
        return CommandResult(False, "Usage: /browser <url>  OR  /browser google <search>")
    try:
        subprocess.run(["which", "w3m"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        return CommandResult(False, "w3m not found — install with: sudo pacman -S w3m")

    if args[0].lower() == "google" and len(args) > 1:
        import urllib.parse

        query = urllib.parse.quote_plus(" ".join(args[1:]))
        url = f"https://www.google.com/search?q={query}"
    else:
        url = args[0] if args[0].startswith(("http://", "https://")) else f"https://{args[0]}"

    try:
        subprocess.run(["w3m", url], cwd=EMILY_ROOT)
        return CommandResult(True, "Browser closed")
    except Exception as exc:
        return CommandResult(False, str(exc))


# ── Parse / dispatch ──────────────────────────────────────────────────────────


def parse_command(text: str) -> tuple[str, list[str]]:
    if not text.startswith("/"):
        return "", []
    parts = text[1:].strip().split()
    if not parts:
        return "", []
    return parts[0].lower(), parts[1:]


async def execute_command(text: str) -> CommandResult:
    cmd, args = parse_command(text)
    if not cmd:
        return CommandResult(False, "Invalid command")
    fn = registry.get_command(cmd)
    if not fn:
        return CommandResult(False, f"Unknown command /{cmd} — try /help")
    try:
        return await fn(args)
    except Exception as exc:
        log.error("command_failed", command=cmd, error=str(exc))
        return CommandResult(False, f"Command failed: {exc}")
