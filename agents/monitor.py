"""MonitorAgent — system resource monitoring and anomaly detection."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import psutil

from agents.base import BaseAgent
from core.bus import Message, Priority
from observability.logger import get_logger
from observability.metrics import RAM_USED_GB, VRAM_USED_GB

log = get_logger(__name__)


class MonitorAgent(BaseAgent):
    """
    Monitors system resources and Emily's own performance metrics.

    Runs a background polling loop that updates Prometheus metrics
    and sends alerts if resource usage exceeds thresholds.
    """

    name = "MonitorAgent"
    description = "System resource monitoring, anomaly detection, and alerting."

    _CPU_THRESHOLD = 95.0
    _RAM_THRESHOLD_GB = 55.0  # Alert at 55/62 GB
    _VRAM_THRESHOLD_GB = 22.0  # Alert at 22/24 GB

    def __init__(self, bus: Any, fleet: Any, memory: Any) -> None:
        super().__init__(bus, fleet, memory)
        self._heartbeats: dict[str, float] = {}

    async def start(self) -> None:
        """Start the agent and the background monitoring loop."""
        await super().start()
        asyncio.create_task(self._monitoring_loop(), name="monitor_resource_loop")

    async def handle(self, message: Message) -> None:
        """Handle monitoring requests and heartbeats."""
        if message.type == "agent.heartbeat":
            agent_name = message.payload.get("agent", "unknown")
            self._heartbeats[agent_name] = time.time()

        elif message.type == "monitor.status_request":
            await self._send_status_report(message)

    async def _monitoring_loop(self) -> None:
        """Background loop that polls system metrics every 30 seconds."""
        while self._running:
            try:
                await self._collect_and_update_metrics()
            except Exception as exc:
                self._log.error("monitoring_error", error=str(exc))
            await asyncio.sleep(30)

    async def _collect_and_update_metrics(self) -> None:
        """Collect system metrics and update Prometheus gauges."""
        # RAM
        ram = psutil.virtual_memory()
        ram_used_gb = ram.used / 1e9
        RAM_USED_GB.set(ram_used_gb)

        # CPU
        cpu_percent = await asyncio.to_thread(psutil.cpu_percent, interval=1)

        # VRAM (if nvidia-smi available)
        vram_gb = await self._get_vram_gb()
        if vram_gb > 0:
            VRAM_USED_GB.set(vram_gb)

        # Alerts
        if cpu_percent >= self._CPU_THRESHOLD:
            self._log.warning("high_cpu_usage", cpu_percent=f"{cpu_percent:.1f}%")

        if ram_used_gb >= self._RAM_THRESHOLD_GB:
            self._log.warning("high_ram_usage", ram_used_gb=f"{ram_used_gb:.1f}")

        if vram_gb >= self._VRAM_THRESHOLD_GB:
            self._log.warning("high_vram_usage", vram_gb=f"{vram_gb:.1f}")

        self._log.debug(
            "system_metrics",
            cpu=f"{cpu_percent:.1f}%",
            ram_gb=f"{ram_used_gb:.1f}",
            vram_gb=f"{vram_gb:.1f}",
        )

    async def _get_vram_gb(self) -> float:
        """Query VRAM usage via nvidia-smi."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            if proc.returncode == 0:
                mb = float(stdout.decode().strip())
                return mb / 1024.0
        except Exception:
            pass
        return 0.0

    async def _send_status_report(self, message: Message) -> None:
        """Send a system status report."""
        ram = psutil.virtual_memory()
        status = {
            "cpu_percent": psutil.cpu_percent(),
            "ram_used_gb": round(ram.used / 1e9, 2),
            "ram_total_gb": round(ram.total / 1e9, 2),
            "agent_heartbeats": dict(self._heartbeats),
            "uptime_s": time.time() - min(self._heartbeats.values()) if self._heartbeats else 0,
        }
        await self.send(
            message.sender,
            "monitor.status_report",
            status,
            priority=Priority.ACTIVE,
            task_id=message.task_id,
        )
