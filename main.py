"""
Emily — Cognitive AI Voice Operating System
Entry point and CLI.

Supports two modes:
  --gui    (default)  Launch the Brain Dashboard (PySide6) alongside Emily
  --no-gui            Headless mode — voice-only, no desktop GUI
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from observability.logger import get_logger

log = get_logger(__name__)


async def _run_emily_headless(config_path: str = "config.yaml") -> None:
    """Start and run Emily until a shutdown signal is received (no GUI)."""
    from core.bootstrap import Bootstrap

    async with Bootstrap.create(config_path) as emily:
        log.info("emily_main_loop_started")
        await emily.run_until_shutdown()


def _run_emily_gui(config_path: str = "config.yaml") -> None:
    """Start Emily with the Brain + Voice Dashboards (PySide6)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from core.async_bridge import AsyncRunner
    from core.brain_hub import BrainEventHub, set_brain_hub
    from ui.brain.dashboard import BrainDashboard
    from ui.voice.dashboard import VoiceDashboard
    from ui.voice.poller import VoiceEnginePoller

    app = QApplication(sys.argv)
    app.setApplicationName("Emily Dashboards")
    app.setOrganizationName("Emily")
    app.setApplicationVersion("1.0.0")

    hub = BrainEventHub()
    set_brain_hub(hub)

    runner = AsyncRunner()
    runner.start()

    brain_dashboard = BrainDashboard(hub)
    brain_dashboard.show()

    voice_poller = VoiceEnginePoller()
    voice_dashboard = VoiceDashboard(voice_poller, brain_hub=hub)
    voice_dashboard.show()
    voice_poller.start()

    boot_ready: dict[str, object] = {}

    def _try_wire_engine() -> None:
        """Check periodically if bootstrap has started and wire the voice engine."""
        bootstrap = boot_ready.get("bootstrap")
        if bootstrap is None:
            return
        engine = getattr(bootstrap, "voice_engine_instance", None)
        if engine is not None and voice_poller._engine is None:
            voice_poller.set_engine(engine)
            _wire_timer.stop()
            log.info("voice_dashboard_engine_wired")
        elif not getattr(bootstrap, "_shutdown_event", None):
            return
        elif bootstrap._shutdown_event.is_set():
            _wire_timer.stop()

    _wire_timer = QTimer()
    _wire_timer.setInterval(500)
    _wire_timer.timeout.connect(_try_wire_engine)
    _wire_timer.start()

    async def _bootstrap_main() -> None:
        from core.bootstrap import Bootstrap
        from observability.logger import configure_logging

        configure_logging(log_level="INFO", log_format="json", brain_tap=True)

        async with Bootstrap.create(config_path, brain_hub=hub) as emily:
            boot_ready["bootstrap"] = emily
            log.info("emily_main_loop_started")
            await emily.run_until_shutdown()

    runner.submit(_bootstrap_main())

    def _on_error(tok: str, tb: str) -> None:
        log.error("bootstrap_gui_error", traceback=tb[:2000])

    runner.error_occurred.connect(_on_error)

    def _on_quit() -> None:
        voice_poller.stop()
        bootstrap = boot_ready.get("bootstrap")
        if bootstrap is not None and hasattr(bootstrap, "_shutdown_event"):
            bootstrap._shutdown_event.set()  # type: ignore[union-attr]
        runner.shutdown()

    app.aboutToQuit.connect(_on_quit)

    sys.exit(app.exec())


def cli() -> None:
    """Console script entry point."""
    parser = argparse.ArgumentParser(description="Emily — Cognitive AI Voice OS")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml",
    )
    gui_group = parser.add_mutually_exclusive_group()
    gui_group.add_argument(
        "--gui",
        action="store_true",
        default=True,
        help="Launch with Brain Dashboard GUI (default)",
    )
    gui_group.add_argument(
        "--no-gui",
        action="store_true",
        help="Headless mode — voice only, no desktop GUI",
    )
    args = parser.parse_args()

    if args.no_gui:
        try:
            asyncio.run(_run_emily_headless(args.config))
        except KeyboardInterrupt:
            print("\nEmily stopped.")
    else:
        try:
            _run_emily_gui(args.config)
        except KeyboardInterrupt:
            print("\nEmily stopped.")
        except ImportError as exc:
            print(f"PySide6 not installed — falling back to headless mode: {exc}")
            try:
                asyncio.run(_run_emily_headless(args.config))
            except KeyboardInterrupt:
                print("\nEmily stopped.")


if __name__ == "__main__":
    cli()
