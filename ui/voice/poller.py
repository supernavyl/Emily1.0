"""
VoiceEnginePoller — QTimer-driven data reader for the desktop Voice Dashboard.

Reads attributes directly from the in-process VoiceEngine every 500ms
and emits a snapshot dict via a Qt signal so widgets can update.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from observability.logger import get_logger

log = get_logger(__name__)


class VoiceEnginePoller(QObject):
    """
    Polls VoiceEngine attributes on a 500ms timer and emits structured snapshots.

    Call ``set_engine(engine)`` once the bootstrap has created the VoiceEngine.
    Until then, the poller emits empty/default snapshots.
    """

    data_updated = Signal(dict)
    transcript_received = Signal(str, str)

    _INTERVAL_MS = 500

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine: Any | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._last_transcript_count = 0
        self._start_time = time.monotonic()

    def set_engine(self, engine: Any) -> None:
        """Wire the poller to a live VoiceEngine instance."""
        self._engine = engine
        self._start_time = time.monotonic()
        log.info("voice_poller_engine_set")

    def start(self) -> None:
        """Begin polling."""
        self._timer.start()

    def stop(self) -> None:
        """Stop polling."""
        self._timer.stop()

    def _poll(self) -> None:
        """Read all voice engine data and emit ``data_updated``."""
        snapshot: dict[str, Any] = {
            "fsm_state": "N/A",
            "state_duration_s": 0.0,
            "running": False,
            "engine_available": self._engine is not None,
            "uptime_s": time.monotonic() - self._start_time,
            "emotion": None,
            "turn_signal": None,
            "rhythm": None,
            "pipeline_modules": {},
            "speakers": {"list": [], "total_tracked": 0},
            "stats": {},
            "tts_available": False,
            "tts_provider": "N/A",
            "stt_available": False,
            "stt_model": "N/A",
            "snr_db": None,
        }

        if self._engine is None:
            self.data_updated.emit(snapshot)
            return

        fsm = _safe_attr(self._engine, "fsm")
        modules = _safe_attr(self._engine, "_modules") or {}

        if fsm is not None:
            state = _safe_attr(fsm, "state")
            snapshot["fsm_state"] = state.name if state is not None else "N/A"
            snapshot["state_duration_s"] = round(_safe_attr(fsm, "state_duration_s") or 0.0, 1)
        snapshot["running"] = bool(_safe_attr(self._engine, "is_running"))

        snapshot["emotion"] = _read_emotion(fsm)
        snapshot["turn_signal"] = _read_turn_signal(fsm)
        snapshot["rhythm"] = _read_rhythm(fsm)
        snapshot["pipeline_modules"] = _read_pipeline(modules)
        snapshot["speakers"] = _read_speakers(modules)
        snapshot["stats"] = _read_stats(fsm)

        tts = modules.get("tts_engine")
        if tts is not None:
            snapshot["tts_available"] = True
            snapshot["tts_provider"] = (
                _safe_attr(tts, "_active_engine") or _safe_attr(tts, "active_engine") or "tts"
            )

        stt = modules.get("streaming_stt")
        if stt is not None:
            snapshot["stt_available"] = True
            snapshot["stt_model"] = _safe_attr(stt, "_model_name") or "whisper"

        noise = modules.get("noise_suppress")
        if noise is not None:
            snr_mon = _safe_attr(noise, "_snr_monitor")
            if snr_mon is not None:
                snapshot["snr_db"] = round(_safe_attr(snr_mon, "current_snr_db") or 0.0, 1)

        capture = modules.get("audio_capture")
        if capture is not None:
            cfg = _safe_attr(capture, "_config")
            snapshot["current_input_device"] = _safe_attr(cfg, "input_device")
            snapshot["current_output_device"] = _safe_attr(cfg, "output_device")

        snapshot["mic_level"] = self._read_mic_level(modules)
        snapshot["stt_partial"] = self._read_stt_partial(fsm)

        self._check_new_transcript(stt)
        self.data_updated.emit(snapshot)

    def change_device(self, device_type: str, device_index: int | None) -> None:
        """Switch the mic or speaker on the running AudioCaptureEngine.

        Args:
            device_type: ``"input"`` for microphone, ``"output"`` for speaker.
            device_index: sounddevice device index, or None for system default.
        """
        if self._engine is None:
            log.warning("change_device_no_engine")
            return

        modules = _safe_attr(self._engine, "_modules") or {}
        capture = modules.get("audio_capture")
        if capture is None:
            log.warning("change_device_no_capture")
            return

        async def _switch() -> None:
            try:
                await capture.stop()
                cfg = capture._config
                if device_type == "input":
                    cfg.input_device = device_index
                else:
                    cfg.output_device = device_index
                await capture.start()
                log.info("device_switched", type=device_type, device=device_index)
            except Exception as exc:
                log.error("device_switch_failed", error=str(exc))

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_switch())
        except RuntimeError:
            log.warning("change_device_no_event_loop")

    def _read_stt_partial(self, fsm: Any) -> str:
        """Read the current STT partial transcript from the FSM."""
        if fsm is None:
            return ""
        stt_frame = _safe_attr(fsm, "_current_stt_frame")
        if stt_frame is None:
            return ""
        return _safe_attr(stt_frame, "partial_text") or ""

    def _read_mic_level(self, modules: dict[str, Any]) -> float:
        """Compute RMS energy from the most recent audio capture chunk."""
        capture = modules.get("audio_capture")
        if capture is None:
            return 0.0
        chunk = _safe_attr(capture, "_current_chunk")
        if chunk is None:
            return 0.0
        data = _safe_attr(chunk, "data")
        if data is None:
            return 0.0
        try:
            import numpy as np

            arr = np.asarray(data, dtype=np.float32)
            if arr.size == 0:
                return 0.0
            return float(np.sqrt(np.mean(arr**2)))
        except Exception:
            return 0.0

    def _check_new_transcript(self, stt: Any) -> None:
        """Detect new committed utterances and emit transcript_received."""
        if stt is None:
            return
        count = _safe_attr(stt, "_committed_count") or 0
        if count > self._last_transcript_count:
            text = _safe_attr(stt, "_last_committed_text") or ""
            if text:
                self.transcript_received.emit("user", text)
            self._last_transcript_count = count


def _safe_attr(obj: Any, name: str) -> Any:
    """Read an attribute without raising."""
    try:
        return getattr(obj, name, None)
    except Exception:
        return None


def _read_emotion(fsm: Any) -> dict[str, Any] | None:
    """Extract emotion state from the FSM."""
    if fsm is None:
        return None
    emotion = _safe_attr(fsm, "_current_emotion")
    if emotion is None:
        return None
    try:
        return {
            "primary": getattr(emotion, "primary", None),
            "confidence": round(getattr(emotion, "confidence", 0.0), 3),
            "valence": round(getattr(emotion, "valence", 0.0), 3),
            "arousal": round(getattr(emotion, "arousal", 0.0), 3),
            "cognitive_load": round(getattr(emotion, "cognitive_load", 0.0), 3),
            "engagement": round(getattr(emotion, "engagement", 0.0), 3),
        }
    except Exception:
        return None


def _read_turn_signal(fsm: Any) -> dict[str, Any] | None:
    """Extract the latest turn detection signal."""
    if fsm is None:
        return None
    detector = _safe_attr(fsm, "_turn_detector")
    if detector is None:
        return None
    signal = _safe_attr(detector, "last_signal")
    if signal is None:
        return None
    try:
        return {
            "score": round(getattr(signal, "score", 0.0), 3),
            "action": getattr(signal, "action", None),
            "breakdown": {
                k: round(v, 3)
                for k, v in (getattr(signal, "confidence_breakdown", {}) or {}).items()
            },
        }
    except Exception:
        return None


def _read_rhythm(fsm: Any) -> dict[str, Any] | None:
    """Extract rhythm synchronization data."""
    if fsm is None:
        return None
    rhythm = _safe_attr(fsm, "_rhythm_sync")
    if rhythm is None:
        return None
    try:
        targets = rhythm.get_targets()
        profile = rhythm.user_profile
        return {
            "user": {
                "speaking_rate": round(getattr(profile, "speaking_rate_syl_s", 0.0), 2),
                "pause_ms": round(getattr(profile, "pause_duration_ms", 0.0), 1),
                "latency_ms": round(getattr(profile, "response_latency_ms", 0.0), 1),
            },
            "emily": {
                "speaking_rate": round(getattr(targets, "speaking_rate_syl_s", 0.0), 2),
                "pause_ms": round(getattr(targets, "pause_duration_ms", 0.0), 1),
                "phrase_words": getattr(targets, "phrase_length_words", 0),
                "latency_ms": round(getattr(targets, "response_latency_ms", 0.0), 1),
            },
            "entrainment": getattr(rhythm, "entrainment_degree", 0.0),
        }
    except Exception:
        return None


def _read_pipeline(modules: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build per-module status dict."""
    result: dict[str, dict[str, Any]] = {}
    for name, mod in modules.items():
        info: dict[str, Any] = {"loaded": mod is not None}
        if name == "audio_capture":
            cfg = _safe_attr(mod, "_config")
            info["input_rate"] = _safe_attr(cfg, "input_sample_rate")
            info["output_rate"] = _safe_attr(cfg, "output_sample_rate")
            info["chunk_ms"] = _safe_attr(cfg, "input_chunk_ms")
        elif name == "aec":
            cfg = _safe_attr(mod, "_config")
            info["tail_ms"] = _safe_attr(cfg, "tail_length_ms")
            info["sample_rate"] = _safe_attr(cfg, "sample_rate")
        elif name == "noise_suppress":
            snr_mon = _safe_attr(mod, "_snr_monitor")
            info["snr_db"] = round(_safe_attr(snr_mon, "current_snr_db") or 0.0, 1)
            info["mode"] = _safe_attr(mod, "_active_mode") or "unknown"
        elif name == "streaming_stt":
            info["model"] = _safe_attr(mod, "_model_name")
        elif name == "speaker_engine":
            info["max_speakers"] = _safe_attr(mod, "_max_speakers")
            active = _safe_attr(mod, "_active_speakers") or []
            info["active_count"] = len(active)
        result[name] = info
    return result


def _read_speakers(modules: dict[str, Any]) -> dict[str, Any]:
    """Extract active speaker list."""
    speaker_engine = modules.get("speaker_engine")
    if speaker_engine is None:
        return {"list": [], "total_tracked": 0}
    active = _safe_attr(speaker_engine, "_active_speakers") or []
    speakers = []
    for s in active:
        speakers.append(
            {
                "id": _safe_attr(s, "speaker_id"),
                "label": _safe_attr(s, "label"),
                "confidence": round(_safe_attr(s, "confidence") or 0.0, 3),
                "is_primary": bool(_safe_attr(s, "is_primary")),
            }
        )
    return {"list": speakers, "total_tracked": len(speakers)}


def _read_stats(fsm: Any) -> dict[str, Any]:
    """Extract aggregate session statistics."""
    stats: dict[str, Any] = {}
    if fsm is None:
        return stats
    bc = _safe_attr(fsm, "_backchannel_engine")
    if bc is not None:
        stats["backchannels"] = _safe_attr(bc, "session_count") or 0
    interrupt = _safe_attr(fsm, "_interrupt_handler")
    if interrupt is not None:
        stats["interrupts"] = _safe_attr(interrupt, "interrupt_count") or 0
    return stats
