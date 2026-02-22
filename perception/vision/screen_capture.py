"""
Screen capture for Emily's vision pipeline.

Captures periodic screenshots and emits them as base64-encoded images
to the PerceptionBus for MiniCPM-V analysis.
"""

from __future__ import annotations

import asyncio
import base64
import io
import time
from typing import Any, AsyncIterator

from config import VisionConfig
from observability.logger import get_logger

log = get_logger(__name__)


class ScreenCapture:
    """
    Periodic screen capture using mss (multi-screen shot).

    Captures the primary monitor at configurable intervals.
    Returns screenshots as base64-encoded PNG strings.
    """

    _MAX_CONSECUTIVE_ERRORS = 3

    def __init__(self, config: VisionConfig) -> None:
        """
        Args:
            config: Vision configuration.
        """
        self._config = config
        self._available = False
        self._sct: object | None = None
        self._consecutive_errors = 0

    async def init(self) -> None:
        """Initialize the screen capture backend."""
        import os

        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            log.info("screen_capture_skipped_wayland_session")
            return

        try:
            import mss  # type: ignore[import-untyped]

            def _try_init() -> object:
                sct = mss.mss()
                sct.grab(sct.monitors[1])
                return sct

            self._sct = await asyncio.to_thread(_try_init)
            self._available = True
            log.info("screen_capture_initialized")
        except ImportError:
            log.warning("mss_not_installed_screen_capture_disabled")
        except Exception as exc:
            log.warning("screen_capture_init_failed", error=str(exc))
            self._sct = None

    async def capture_once(self) -> str | None:
        """
        Capture a single screenshot.

        Returns:
            Base64-encoded PNG string, or None if capture failed.
        """
        if not self._available or self._sct is None:
            return None

        def _capture() -> bytes:
            from PIL import Image  # type: ignore[import-untyped]
            monitor = self._sct.monitors[1]  # type: ignore[union-attr]
            screenshot = self._sct.grab(monitor)  # type: ignore[union-attr]
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            # Resize to max 1024px wide for efficient vision model inference
            if img.width > 1024:
                ratio = 1024 / img.width
                img = img.resize((1024, int(img.height * ratio)))
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()

        try:
            png_bytes = await asyncio.to_thread(_capture)
            self._consecutive_errors = 0
            return base64.b64encode(png_bytes).decode()
        except Exception as exc:
            self._consecutive_errors += 1
            log.error("screen_capture_error", error=str(exc))
            if self._consecutive_errors >= self._MAX_CONSECUTIVE_ERRORS:
                log.warning("screen_capture_disabled_after_repeated_errors")
                self._available = False
            return None

    async def stream(self) -> AsyncIterator[tuple[str, float]]:
        """
        Continuously capture screenshots at the configured interval.

        Yields:
            Tuple of (base64_png_string, timestamp).
        """
        while True:
            image_b64 = await self.capture_once()
            if image_b64:
                yield image_b64, time.time()
            await asyncio.sleep(self._config.screen_capture_interval_s)

    def close(self) -> None:
        """Release screen capture resources."""
        if self._sct:
            try:
                self._sct.close()  # type: ignore[union-attr]
            except Exception:
                pass
