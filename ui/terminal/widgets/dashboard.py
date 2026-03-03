"""
Dashboard panel for system monitoring visualization.
"""

from __future__ import annotations

import subprocess
from typing import ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import ProgressBar, Static

try:
    import psutil
except ImportError:
    psutil = None


class DashboardPanel(Vertical):
    """System monitoring dashboard with visual indicators."""

    DEFAULT_CSS = """
    DashboardPanel {
        height: 100%;
        border: round $primary;
        background: $panel;
        padding: 1;
    }

    .dashboard-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin: 0 0 1 0;
    }

    .metric-row {
        height: auto;
        margin: 0 0 1 0;
    }

    .metric-label {
        width: 8;
        content-align: left middle;
        color: $text;
    }

    .metric-value {
        width: 6;
        content-align: right middle;
        color: $accent;
        text-style: bold;
    }

    .metric-bar {
        width: 1fr;
    }

    ProgressBar {
        height: 1;
    }

    .progress--complete {
        background: $success;
    }

    .progress--75 {
        background: $warning;
    }

    .progress--50 {
        background: $primary;
    }

    .progress--25 {
        background: $error;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    cpu_percent: reactive[float] = reactive(0.0)
    memory_percent: reactive[float] = reactive(0.0)
    disk_percent: reactive[float] = reactive(0.0)
    vram_used: reactive[float] = reactive(0.0)
    vram_total: reactive[float] = reactive(0.0)
    network_sent: reactive[int] = reactive(0)
    network_recv: reactive[int] = reactive(0)
    process_count: reactive[int] = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.last_network_stats = None

    def compose(self):
        """Compose the dashboard."""
        yield Static("SYSTEM MONITOR", classes="dashboard-title")

        # CPU Usage
        with Horizontal(classes="metric-row"):
            yield Static("CPU:", classes="metric-label")
            yield Static("0%", classes="metric-value", id="cpu-value")
            yield ProgressBar(total=100, show_eta=False, classes="metric-bar", id="cpu-bar")

        # Memory Usage
        with Horizontal(classes="metric-row"):
            yield Static("MEM:", classes="metric-label")
            yield Static("0%", classes="metric-value", id="memory-value")
            yield ProgressBar(total=100, show_eta=False, classes="metric-bar", id="memory-bar")

        # Disk Usage
        with Horizontal(classes="metric-row"):
            yield Static("DISK:", classes="metric-label")
            yield Static("0%", classes="metric-value", id="disk-value")
            yield ProgressBar(total=100, show_eta=False, classes="metric-bar", id="disk-bar")

        # GPU VRAM
        with Horizontal(classes="metric-row"):
            yield Static("VRAM:", classes="metric-label")
            yield Static("—", classes="metric-value", id="vram-value")
            yield ProgressBar(total=100, show_eta=False, classes="metric-bar", id="vram-bar")

        # Network I/O
        with Horizontal(classes="metric-row"):
            yield Static("NET:", classes="metric-label")
            yield Static("↑0 ↓0", classes="metric-value", id="network-value")

        # Process Count
        with Horizontal(classes="metric-row"):
            yield Static("PROCS:", classes="metric-label")
            yield Static("0", classes="metric-value", id="process-value")

    def on_mount(self) -> None:
        """Start the update timer."""
        self.set_interval(2.0, self.update_metrics)
        self.update_metrics()

    def update_metrics(self) -> None:
        """Update all system metrics."""
        if not psutil:
            return

        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=None)
            self.cpu_percent = float(cpu_percent) if isinstance(cpu_percent, int | float) else 0.0

            # Memory
            memory = psutil.virtual_memory()
            self.memory_percent = memory.percent

            # Disk
            disk = psutil.disk_usage("/")
            self.disk_percent = (disk.used / disk.total) * 100

            # GPU VRAM via nvidia-smi (no extra Python package needed)
            try:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,memory.total",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split("\n")[0].split(",")
                    self.vram_used = float(parts[0].strip()) / 1024
                    self.vram_total = float(parts[1].strip()) / 1024
            except Exception:
                pass

            # Network
            net_io = psutil.net_io_counters()
            if (
                self.last_network_stats
                and hasattr(net_io, "bytes_sent")
                and hasattr(self.last_network_stats, "bytes_sent")
            ):
                sent_delta = net_io.bytes_sent - self.last_network_stats.bytes_sent
                recv_delta = net_io.bytes_recv - self.last_network_stats.bytes_recv
                self.network_sent = sent_delta
                self.network_recv = recv_delta
            self.last_network_stats = net_io

            # Processes
            self.process_count = len(psutil.pids())

        except Exception:
            pass

    def watch_cpu_percent(self, value: float) -> None:
        """Update CPU display."""
        value_widget = self.query_one("#cpu-value", Static)
        bar_widget = self.query_one("#cpu-bar", ProgressBar)

        value_widget.update(f"{value:.1f}%")
        bar_widget.progress = value

        # Color coding
        if value > 80:
            bar_widget.styles.background = "red"
        elif value > 60:
            bar_widget.styles.background = "yellow"
        else:
            bar_widget.styles.background = "green"

    def watch_memory_percent(self, value: float) -> None:
        """Update memory display."""
        value_widget = self.query_one("#memory-value", Static)
        bar_widget = self.query_one("#memory-bar", ProgressBar)

        value_widget.update(f"{value:.1f}%")
        bar_widget.progress = value

        # Color coding
        if value > 85:
            bar_widget.styles.background = "red"
        elif value > 70:
            bar_widget.styles.background = "yellow"
        else:
            bar_widget.styles.background = "cyan"

    def watch_disk_percent(self, value: float) -> None:
        """Update disk display."""
        value_widget = self.query_one("#disk-value", Static)
        bar_widget = self.query_one("#disk-bar", ProgressBar)

        value_widget.update(f"{value:.1f}%")
        bar_widget.progress = value

        # Color coding
        if value > 90:
            bar_widget.styles.background = "red"
        elif value > 75:
            bar_widget.styles.background = "yellow"
        else:
            bar_widget.styles.background = "blue"

    def watch_vram_used(self, value: float) -> None:
        """Update GPU VRAM display."""
        value_widget = self.query_one("#vram-value", Static)
        bar_widget = self.query_one("#vram-bar", ProgressBar)
        if self.vram_total > 0:
            pct = (value / self.vram_total) * 100
            value_widget.update(f"{value:.1f}G")
            bar_widget.total = 100
            bar_widget.progress = pct
            if pct > 92:
                bar_widget.styles.background = "red"
            elif pct > 75:
                bar_widget.styles.background = "yellow"
            else:
                bar_widget.styles.background = "magenta"
        else:
            value_widget.update("—")

    def _update_network_widget(self) -> None:
        network_widget = self.query_one("#network-value", Static)
        sent_mb = self.network_sent / (1024 * 1024)
        recv_mb = self.network_recv / (1024 * 1024)
        network_widget.update(f"↑{sent_mb:.1f} ↓{recv_mb:.1f}")

    def watch_network_sent(self, value: int) -> None:
        """Update network display."""
        self._update_network_widget()

    def watch_network_recv(self, value: int) -> None:
        """Update network display when recv changes."""
        self._update_network_widget()

    def watch_process_count(self, value: int) -> None:
        """Update process count display."""
        process_widget = self.query_one("#process-value", Static)
        process_widget.update(str(value))

    def action_refresh(self) -> None:
        """Force refresh all metrics."""
        self.update_metrics()
