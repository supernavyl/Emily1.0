"""
Status bar — real-time CPU, RAM, GPU VRAM, API health, and clock.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

try:
    import psutil
except ImportError:
    psutil = None

API_BASE = "http://localhost:8001"


class StatusBar(Vertical):
    """Sidebar status panel with system + Emily indicators."""

    DEFAULT_CSS = """
    StatusBar {
        height: 100%;
        background: $panel;
        color: $text-muted;
        padding: 1 1;
    }

    .sb-title {
        text-style: bold;
        color: $primary;
        text-align: center;
        margin: 0 0 1 0;
    }

    .sb-section {
        color: $secondary;
        text-style: bold;
        margin: 1 0 0 0;
    }

    .sb-row {
        color: $text;
    }

    .sb-ok {
        color: $success;
    }

    .sb-warn {
        color: $warning;
    }

    .sb-err {
        color: $error;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("f5", "refresh", "Refresh", show=False),
    ]

    _cpu: reactive[float] = reactive(0.0)
    _mem: reactive[float] = reactive(0.0)
    _vram_used: reactive[float] = reactive(0.0)
    _vram_total: reactive[float] = reactive(0.0)
    _api_ok: reactive[bool | None] = reactive(None)
    _voice_state: reactive[str] = reactive("—")
    _time: reactive[str] = reactive("")

    def compose(self):
        yield Static("◈ EMILY STATUS", classes="sb-title")

        yield Static("── SYSTEM ──", classes="sb-section")
        yield Static("CPU:  0%", classes="sb-row", id="sb-cpu")
        yield Static("RAM:  0%", classes="sb-row", id="sb-ram")
        yield Static("VRAM: —", classes="sb-row", id="sb-vram")
        yield Static("Time: —", classes="sb-row", id="sb-time")

        yield Static("── EMILY ──", classes="sb-section")
        yield Static("API:  —", classes="sb-row", id="sb-api")
        yield Static("Voice: —", classes="sb-row", id="sb-voice")

        yield Static("── BINDINGS ──", classes="sb-section")
        yield Static("F1  Chat", classes="sb-row")
        yield Static("F2  Dashboard", classes="sb-row")
        yield Static("F3  Memory", classes="sb-row")
        yield Static("F4  Logs", classes="sb-row")
        yield Static("F5  Refresh", classes="sb-row")
        yield Static("F6  Voice", classes="sb-row")
        yield Static("^N  New conv", classes="sb-row")
        yield Static("^L  Clear", classes="sb-row")

    def on_mount(self) -> None:
        self.set_interval(3.0, self._update_sys)
        self.set_interval(5.0, self._update_emily)
        self._update_sys()
        self.call_after_refresh(self._update_emily)

    # ── System metrics ───────────────────────────────────────────────────────

    def _update_sys(self) -> None:
        self._read_cpu_ram()
        self._read_vram()
        self._update_time()

    def _read_cpu_ram(self) -> None:
        if not psutil:
            return
        try:
            self._cpu = float(psutil.cpu_percent(interval=None))
            self._mem = psutil.virtual_memory().percent
        except Exception:
            pass

    def _read_vram(self) -> None:
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("\n")[0].split(",")
                self._vram_used = float(parts[0].strip()) / 1024
                self._vram_total = float(parts[1].strip()) / 1024
        except Exception:
            pass

    def _update_time(self) -> None:
        self._time = datetime.now().strftime("%H:%M:%S")

    # ── Emily metrics ────────────────────────────────────────────────────────

    async def _update_emily(self) -> None:
        await self._check_api()
        await self._check_voice()

    async def _check_api(self) -> None:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{API_BASE}/api/settings/auth/status")
                self._api_ok = r.is_success
        except Exception:
            self._api_ok = False

    async def _check_voice(self) -> None:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{API_BASE}/api/audio/voice/status")
                if r.is_success:
                    data = r.json()
                    self._voice_state = data.get("state", "idle")
                    return
        except Exception:
            pass
        self._voice_state = "—"

    # ── Watchers ─────────────────────────────────────────────────────────────

    def watch__cpu(self, v: float) -> None:
        w = self.query_one("#sb-cpu", Static)
        bar = "█" * int(v / 10) + "░" * (10 - int(v / 10))
        w.update(f"CPU:  {v:4.1f}%  {bar}")
        cls = "sb-err" if v > 90 else "sb-warn" if v > 70 else "sb-ok"
        w.set_classes(f"sb-row {cls}")

    def watch__mem(self, v: float) -> None:
        w = self.query_one("#sb-ram", Static)
        bar = "█" * int(v / 10) + "░" * (10 - int(v / 10))
        w.update(f"RAM:  {v:4.1f}%  {bar}")
        cls = "sb-err" if v > 90 else "sb-warn" if v > 75 else "sb-ok"
        w.set_classes(f"sb-row {cls}")

    def watch__vram_used(self, v: float) -> None:
        w = self.query_one("#sb-vram", Static)
        if self._vram_total > 0:
            pct = v / self._vram_total
            bar = "█" * int(pct * 10) + "░" * (10 - int(pct * 10))
            w.update(f"VRAM: {v:.1f}/{self._vram_total:.0f}GB {bar}")
            cls = "sb-err" if pct > 0.92 else "sb-warn" if pct > 0.75 else "sb-ok"
            w.set_classes(f"sb-row {cls}")
        else:
            w.update("VRAM: —")

    def watch__time(self, v: str) -> None:
        self.query_one("#sb-time", Static).update(f"Time: {v}")

    def watch__api_ok(self, v: bool | None) -> None:
        w = self.query_one("#sb-api", Static)
        if v is True:
            w.update("API:  ● online")
            w.set_classes("sb-row sb-ok")
        elif v is False:
            w.update("API:  ○ offline")
            w.set_classes("sb-row sb-err")
        else:
            w.update("API:  — checking")
            w.set_classes("sb-row")

    def watch__voice_state(self, v: str) -> None:
        w = self.query_one("#sb-voice", Static)
        active_states = {"listening", "processing", "speaking", "interrupted", "filling"}
        if v.lower() in active_states:
            w.update(f"Voice: ◉ {v}")
            w.set_classes("sb-row sb-ok")
        else:
            w.update(f"Voice: ○ {v}")
            w.set_classes("sb-row")

    def action_refresh(self) -> None:
        self._update_sys()
        self.call_after_refresh(self._update_emily)
