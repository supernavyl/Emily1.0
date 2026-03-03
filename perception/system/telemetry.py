"""
System telemetry perception module.

Collects CPU, RAM, GPU, disk, and network metrics via psutil and
nvidia-smi, publishing periodic snapshots to the PerceptionBus.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import psutil

from observability.logger import get_logger
from observability.metrics import RAM_USED_GB, VRAM_USED_GB

log = get_logger(__name__)


@dataclass
class SystemSnapshot:
    """Point-in-time system resource snapshot."""

    cpu_percent: float = 0.0
    ram_used_gb: float = 0.0
    ram_total_gb: float = 0.0
    ram_percent: float = 0.0
    vram_used_gb: float = 0.0
    vram_total_gb: float = 0.0
    disk_used_gb: float = 0.0
    disk_free_gb: float = 0.0
    net_sent_mb: float = 0.0
    net_recv_mb: float = 0.0
    gpu_temp_c: float = 0.0
    cpu_temp_c: float = 0.0
    load_avg_1m: float = 0.0
    process_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for bus publishing."""
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_used_gb": round(self.ram_used_gb, 2),
            "ram_total_gb": round(self.ram_total_gb, 2),
            "ram_percent": round(self.ram_percent, 1),
            "vram_used_gb": round(self.vram_used_gb, 2),
            "vram_total_gb": round(self.vram_total_gb, 2),
            "disk_used_gb": round(self.disk_used_gb, 1),
            "disk_free_gb": round(self.disk_free_gb, 1),
            "gpu_temp_c": round(self.gpu_temp_c, 1),
            "cpu_temp_c": round(self.cpu_temp_c, 1),
            "load_avg_1m": round(self.load_avg_1m, 2),
            "process_count": self.process_count,
        }


class SystemTelemetry:
    """
    Periodically collects system resource metrics.

    All blocking psutil/subprocess calls are offloaded via asyncio.to_thread
    to avoid blocking the event loop.
    """

    def __init__(self, poll_interval_s: float = 5.0) -> None:
        """
        Args:
            poll_interval_s: Seconds between telemetry snapshots.
        """
        self._poll_interval = poll_interval_s
        self._running = False
        self._latest: SystemSnapshot = SystemSnapshot()
        self._bus: Any | None = None

    def set_bus(self, bus: Any) -> None:
        """Attach a PerceptionBus for event publishing."""
        self._bus = bus

    @property
    def latest(self) -> SystemSnapshot:
        """Most recent telemetry snapshot."""
        return self._latest

    async def collect(self) -> SystemSnapshot:
        """
        Collect a single telemetry snapshot.

        Returns:
            SystemSnapshot with current metrics.
        """
        snap = await asyncio.to_thread(self._collect_sync)
        vram = await self._get_vram()
        snap.vram_used_gb = vram[0]
        snap.vram_total_gb = vram[1]

        VRAM_USED_GB.set(snap.vram_used_gb)
        RAM_USED_GB.set(snap.ram_used_gb)

        self._latest = snap
        return snap

    @staticmethod
    def _collect_sync() -> SystemSnapshot:
        """Synchronous collection of CPU/RAM/disk/network metrics."""
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        load = psutil.getloadavg()

        cpu_temp = 0.0
        try:
            temps = psutil.sensors_temperatures()
            for entries in temps.values():
                for entry in entries:
                    if entry.current > cpu_temp:
                        cpu_temp = entry.current
        except (AttributeError, RuntimeError):
            pass

        return SystemSnapshot(
            cpu_percent=psutil.cpu_percent(interval=None),
            ram_used_gb=mem.used / (1024**3),
            ram_total_gb=mem.total / (1024**3),
            ram_percent=mem.percent,
            disk_used_gb=disk.used / (1024**3),
            disk_free_gb=disk.free / (1024**3),
            net_sent_mb=net.bytes_sent / (1024**2),
            net_recv_mb=net.bytes_recv / (1024**2),
            cpu_temp_c=cpu_temp,
            load_avg_1m=load[0],
            process_count=len(psutil.pids()),
        )

    @staticmethod
    async def _get_vram() -> tuple[float, float]:
        """Query GPU VRAM via nvidia-smi."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=memory.used,memory.total",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            line = stdout.decode().strip().split("\n")[0]
            used, total = line.split(",")
            return float(used.strip()) / 1024.0, float(total.strip()) / 1024.0
        except Exception:
            return 0.0, 0.0

    async def run(self) -> None:
        """Run the telemetry collection loop."""
        self._running = True
        log.info("system_telemetry_started", interval_s=self._poll_interval)

        while self._running:
            try:
                snap = await self.collect()

                if self._bus is not None:
                    from core.bus import Priority

                    await self._bus.publish(
                        "system.telemetry",
                        snap.to_dict(),
                        Priority.LOW,
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("telemetry_collection_error", error=str(exc))

            await asyncio.sleep(self._poll_interval)

        self._running = False
        log.info("system_telemetry_stopped")

    def stop(self) -> None:
        """Stop the telemetry loop."""
        self._running = False
