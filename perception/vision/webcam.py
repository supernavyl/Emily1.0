"""
Webcam feed capture for Emily's presence detection and facial expression analysis.

Captures frames at a lower frequency than the screen capture.
Used for:
- Presence detection (is the user at the computer?)
- Facial expression analysis via DeepFace
- Emotion signal extraction for user_model.py
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from typing import TYPE_CHECKING, Any

from observability.logger import get_logger

if TYPE_CHECKING:
    from config import VisionConfig

log = get_logger(__name__)


class WebcamCapture:
    """
    OpenCV-based webcam frame capture with DeepFace emotion analysis.

    Frame capture runs in a thread pool to avoid blocking the event loop.
    """

    _CAPTURE_INTERVAL_S = 5.0
    _EMOTION_INTERVAL_S = 15.0  # Run emotion analysis less frequently

    def __init__(self, config: VisionConfig) -> None:
        """
        Args:
            config: Vision configuration.
        """
        self._config = config
        self._cap: object | None = None
        self._available = False
        self._last_emotion_time = 0.0

    async def init(self) -> None:
        """Initialize the webcam capture."""
        if not self._config.enabled:
            return
        try:
            import cv2  # type: ignore[import-untyped]

            def _try_open() -> Any:
                cap = cv2.VideoCapture(self._config.webcam_device)
                if not cap.isOpened():
                    return None
                ret, frame = cap.read()
                if not ret or frame is None:
                    cap.release()
                    return None
                return cap

            cap = await asyncio.to_thread(_try_open)
            if cap is not None:
                self._cap = cap
                self._available = True
                log.info("webcam_initialized", device=self._config.webcam_device)
            else:
                log.warning("webcam_not_available", device=self._config.webcam_device)
        except ImportError:
            log.warning("opencv_not_installed_webcam_disabled")

    async def capture_frame(self) -> tuple[str | None, dict[str, Any]]:
        """
        Capture a single webcam frame.

        Returns:
            Tuple of (base64_jpeg_string | None, metadata_dict).
        """
        if not self._available or self._cap is None:
            return None, {}

        def _read_frame() -> tuple[bool, Any]:
            return self._cap.read()  # type: ignore[union-attr]

        try:
            ret, frame = await asyncio.to_thread(_read_frame)
            if not ret or frame is None:
                return None, {}

            # Convert frame to base64 JPEG
            import cv2

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            img_b64 = base64.b64encode(buf.tobytes()).decode()

            meta: dict[str, Any] = {"timestamp": time.time(), "device": self._config.webcam_device}

            # Run emotion detection periodically
            now = time.time()
            if (
                self._config.emotion_detection
                and now - self._last_emotion_time >= self._EMOTION_INTERVAL_S
            ):
                emotions = await self._analyze_emotions(frame)
                if emotions:
                    meta["emotions"] = emotions
                    self._last_emotion_time = now

            return img_b64, meta
        except Exception as exc:
            log.error("webcam_capture_error", error=str(exc))
            return None, {}

    async def _analyze_emotions(self, frame: Any) -> dict[str, float] | None:
        """
        Run DeepFace emotion analysis on a webcam frame.

        Args:
            frame: OpenCV BGR frame.

        Returns:
            Dict of {emotion: confidence} or None on failure.
        """
        try:
            from deepface import DeepFace  # type: ignore[import-untyped]

            def _analyze() -> dict[str, float]:
                result = DeepFace.analyze(
                    frame,
                    actions=["emotion"],
                    enforce_detection=False,
                    silent=True,
                )
                if isinstance(result, list):
                    result = result[0]
                return result.get("emotion", {})

            emotions = await asyncio.to_thread(_analyze)
            log.debug("emotions_detected", emotions=emotions)
            return emotions
        except ImportError:
            return None
        except Exception as exc:
            log.debug("emotion_analysis_error", error=str(exc))
            return None

    def release(self) -> None:
        """Release the webcam device."""
        if self._cap:
            with contextlib.suppress(Exception):
                self._cap.release()  # type: ignore[union-attr]

    @property
    def is_available(self) -> bool:
        """True if webcam is open and available."""
        return self._available
