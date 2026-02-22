"""
Vision pipeline — orchestrates screen capture, webcam, presence detection,
and MiniCPM-V analysis. Emits structured events to the PerceptionBus.

Event types emitted:
  vision.screen_analysis  — periodic screen understanding
  vision.presence_update  — user presence state changes
  vision.emotion_update   — user facial emotion signals
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from config import VisionConfig
from core.bus import PerceptionBus, Priority
from observability.logger import get_logger
from perception.vision.presence import PresenceDetector, PresenceState
from perception.vision.screen_capture import ScreenCapture
from perception.vision.vision_llm import VisionAnalyzer
from perception.vision.webcam import WebcamCapture

log = get_logger(__name__)


class VisionPipeline:
    """
    Full vision perception pipeline.

    Runs three concurrent loops:
    1. Screen capture + MiniCPM-V scene understanding
    2. Webcam capture + presence detection + DeepFace emotion analysis
    3. Presence polling (even without webcam, via system idle time)

    All analysis results are published to the PerceptionBus.
    """

    def __init__(
        self,
        config: VisionConfig,
        bus: PerceptionBus,
        vision_model: str = "minicpm-v:2.6",
        ollama_url: str = "http://localhost:11434",
    ) -> None:
        """
        Args:
            config: Vision configuration block.
            bus: PerceptionBus for publishing events.
            vision_model: Ollama vision model name.
            ollama_url: Ollama base URL.
        """
        self._config = config
        self._bus = bus
        self._screen = ScreenCapture(config)
        self._webcam = WebcamCapture(config)
        self._presence = PresenceDetector(idle_threshold_s=config.presence_idle_threshold_s)
        self._analyzer = VisionAnalyzer(
            ollama_url=ollama_url,
            vision_model=vision_model,
        )
        self._tasks: list[asyncio.Task[None]] = []
        self._running = False
        self._last_presence_state: PresenceState | None = None

    async def start(self) -> None:
        """Initialize all vision subsystems and start background loops."""
        if not self._config.enabled:
            log.info("vision_pipeline_disabled")
            return

        await self._screen.init()
        await self._webcam.init()

        self._running = True
        self._tasks = [
            asyncio.create_task(self._screen_loop(), name="vision.screen_loop"),
            asyncio.create_task(self._webcam_loop(), name="vision.webcam_loop"),
        ]
        log.info("vision_pipeline_started")

    async def stop(self) -> None:
        """Cancel all vision tasks and release resources."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._screen.close()
        self._webcam.release()
        log.info("vision_pipeline_stopped")

    # -------------------------------------------------------------------------
    # Internal loops
    # -------------------------------------------------------------------------

    async def _screen_loop(self) -> None:
        """Periodic screen capture and analysis loop."""
        log.info("vision.screen_loop_started")
        while self._running:
            try:
                screenshot_b64 = await self._screen.capture_once()
                if screenshot_b64:
                    analysis = await self._analyzer.analyze_screen(screenshot_b64)
                    await self._publish("vision.screen_analysis", {
                        "analysis": analysis,
                        "timestamp": time.time(),
                    }, Priority.BACKGROUND)
                    log.debug("screen_analysis_published", summary=analysis.get("summary", "")[:80])
                await asyncio.sleep(self._config.screen_capture_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("screen_loop_error", error=str(exc))
                await asyncio.sleep(5.0)

    async def _webcam_loop(self) -> None:
        """Webcam capture, presence detection, and emotion analysis loop."""
        log.info("vision.webcam_loop_started")
        while self._running:
            try:
                img_b64, meta = await self._webcam.capture_frame()

                # Run presence update (uses idle time even if no webcam frame)
                presence_info = await self._presence.update(frame=None)

                if presence_info.state != self._last_presence_state:
                    self._last_presence_state = presence_info.state
                    await self._publish("vision.presence_update", {
                        "state": presence_info.state.value,
                        "face_detected": presence_info.face_detected,
                        "system_idle_s": presence_info.system_idle_s,
                        "confidence": presence_info.confidence,
                        "timestamp": presence_info.last_updated,
                    }, Priority.ACTIVE)
                    log.info("presence_state_changed", state=presence_info.state.value)

                # Publish emotion signals if available
                if img_b64 and "emotions" in meta:
                    emotions = meta["emotions"]
                    # Convert DeepFace dict to top emotion
                    top_emotion = max(emotions, key=lambda k: emotions[k], default="neutral")
                    top_conf = emotions.get(top_emotion, 0.5) / 100.0
                    await self._publish("vision.emotion_update", {
                        "primary_emotion": top_emotion,
                        "confidence": top_conf,
                        "all_emotions": emotions,
                        "source": "deepface",
                        "timestamp": time.time(),
                    }, Priority.BACKGROUND)

                await asyncio.sleep(self._config.webcam_capture_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("webcam_loop_error", error=str(exc))
                await asyncio.sleep(5.0)

    async def _publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        priority: Priority,
    ) -> None:
        """Publish a vision event to the PerceptionBus."""
        await self._bus.publish(event_type, payload, priority)
