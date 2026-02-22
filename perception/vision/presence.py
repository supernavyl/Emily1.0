"""
Presence detection for Emily's vision pipeline.

Determines whether the user is at the computer based on:
1. Webcam face detection (cv2 Haar cascade or face_recognition)
2. System activity signals (keyboard/mouse idle time)
3. Audio energy levels
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum, auto

from observability.logger import get_logger

log = get_logger(__name__)


class PresenceState(str, Enum):
    """User presence states."""
    PRESENT = "present"         # User is actively at the computer
    IDLE = "idle"               # User is present but idle
    AWAY = "away"               # User is not detected
    UNKNOWN = "unknown"         # Cannot determine presence


@dataclass
class PresenceInfo:
    """Current presence state and supporting signals."""
    state: PresenceState = PresenceState.UNKNOWN
    face_detected: bool = False
    system_idle_s: float = 0.0
    last_updated: float = field(default_factory=time.time)
    confidence: float = 0.0


class PresenceDetector:
    """
    Determines user presence from webcam face detection and system idle time.

    Uses x11-idle or xprintidle for system idle time on X11/Wayland.
    Uses OpenCV Haar cascade for fast face detection on webcam frames.
    """

    _IDLE_THRESHOLD_S = 120.0    # 2 minutes of system idle → away
    _ACTIVE_THRESHOLD_S = 10.0   # 10s or less idle → active

    def __init__(
        self,
        idle_threshold_s: float = _IDLE_THRESHOLD_S,
    ) -> None:
        """
        Args:
            idle_threshold_s: Seconds of system idle time before marking user as away.
        """
        self._idle_threshold = idle_threshold_s
        self._face_cascade: object | None = None
        self._last_state = PresenceInfo()
        self._cv2_available = False
        self._init_face_detector()

    def _init_face_detector(self) -> None:
        """Load the OpenCV face detector."""
        try:
            import cv2
            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._face_cascade = cv2.CascadeClassifier(path)
            self._cv2_available = True
            log.info("face_detector_initialized")
        except (ImportError, Exception) as exc:
            log.warning("face_detector_unavailable", error=str(exc))

    def detect_face(self, frame: object) -> bool:
        """
        Run face detection on a webcam frame.

        Args:
            frame: OpenCV BGR frame.

        Returns:
            True if at least one face is detected.
        """
        if not self._cv2_available or self._face_cascade is None:
            return False
        try:
            import cv2
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)  # type: ignore[arg-type]
            faces = self._face_cascade.detectMultiScale(  # type: ignore[union-attr]
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48)
            )
            return len(faces) > 0
        except Exception:
            return False

    async def get_system_idle_seconds(self) -> float:
        """
        Query the system idle time using xprintidle or xssstate.

        Returns:
            Idle time in seconds. Returns 0.0 on failure.
        """
        for cmd in (["xprintidle"], ["xssstate", "-i"], ["x11-idle"]):
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2.0)
                raw = stdout.decode().strip()
                # xprintidle returns milliseconds, others return seconds
                idle_val = float(raw)
                if cmd[0] == "xprintidle":
                    idle_val /= 1000.0
                return idle_val
            except (FileNotFoundError, asyncio.TimeoutError, ValueError):
                continue
        return 0.0

    async def update(self, frame: object | None = None) -> PresenceInfo:
        """
        Update presence state from current signals.

        Args:
            frame: Optional current webcam frame for face detection.

        Returns:
            Updated PresenceInfo.
        """
        face_detected = False
        if frame is not None and self._cv2_available:
            face_detected = await asyncio.to_thread(self.detect_face, frame)

        idle_s = await self.get_system_idle_seconds()

        # Determine presence state
        if face_detected:
            state = PresenceState.PRESENT
            confidence = 0.9
        elif idle_s < self._ACTIVE_THRESHOLD_S:
            state = PresenceState.PRESENT
            confidence = 0.75
        elif idle_s < self._idle_threshold:
            state = PresenceState.IDLE
            confidence = 0.6
        else:
            state = PresenceState.AWAY
            confidence = 0.8

        info = PresenceInfo(
            state=state,
            face_detected=face_detected,
            system_idle_s=idle_s,
            last_updated=time.time(),
            confidence=confidence,
        )
        self._last_state = info
        log.debug("presence_updated", state=state.value, idle_s=idle_s, face_detected=face_detected)
        return info

    @property
    def current_state(self) -> PresenceInfo:
        """Last known presence state."""
        return self._last_state
