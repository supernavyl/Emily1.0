"""
Audio device management API routes.

GET  /audio/devices           — list all audio input and output devices
GET  /audio/devices/input     — current input device selection
GET  /audio/devices/output    — current output device selection
PUT  /audio/devices/input     — set input device
PUT  /audio/devices/output    — set output device
GET  /audio/voice/status      — voice pipeline status (auto-detects new vs legacy)
GET  /audio/voice/voices      — list available TTS voices
GET  /audio/voice/settings    — current voice/provider settings
PUT  /audio/voice/settings    — update voice and provider
POST /audio/voice/test-tts    — test TTS with sample text
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


class DeviceInfo(BaseModel):
    """Audio device descriptor."""

    index: int
    name: str
    hostapi: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float
    is_default_input: bool = False
    is_default_output: bool = False


class DeviceListResponse(BaseModel):
    """Response for device listing endpoint."""

    input_devices: list[DeviceInfo]
    output_devices: list[DeviceInfo]
    current_input: str | None
    current_output: str | None


class DeviceSetRequest(BaseModel):
    """Request body for setting a device."""

    device: str | int | None


class VoiceStatusResponse(BaseModel):
    """Voice pipeline status — reports on whichever mode is active."""

    voice_mode: str
    running: bool
    tts_available: bool
    stt_available: bool
    wake_word_available: bool
    current_input_device: str | None
    current_output_device: str | None
    fsm_state: str | None = None
    modules_loaded: list[str] | None = None


_audio_state: dict[str, Any] = {
    "input_device": None,
    "output_device": None,
    "audio_pipeline": None,
    "tts_manager": None,
    "voice_engine": None,
    "tts_voice": "af_heart",
    "tts_provider": "kokoro",
}


def set_audio_state(
    *,
    input_device: str | int | None = None,
    output_device: str | int | None = None,
    audio_pipeline: Any = None,
    tts_manager: Any = None,
    voice_engine: Any = None,
) -> None:
    """Inject runtime audio state from app lifespan or bootstrap."""
    if input_device is not None:
        _audio_state["input_device"] = input_device
    if output_device is not None:
        _audio_state["output_device"] = output_device
    if audio_pipeline is not None:
        _audio_state["audio_pipeline"] = audio_pipeline
    if tts_manager is not None:
        _audio_state["tts_manager"] = tts_manager
    # voice_engine kept for backward compat but not required
    if voice_engine is not None:
        _audio_state["voice_engine"] = voice_engine


def _query_devices() -> tuple[list[DeviceInfo], list[DeviceInfo], int | None, int | None]:
    """Query sounddevice for available audio devices."""
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
    except ImportError as err:
        raise HTTPException(503, "sounddevice not installed") from err

    devices = sd.query_devices()

    try:
        default_input_idx, default_output_idx = sd.default.device
    except Exception:
        default_input_idx = default_output_idx = None

    hostapis = sd.query_hostapis()
    hostapi_names = {i: h["name"] for i, h in enumerate(hostapis)}

    inputs: list[DeviceInfo] = []
    outputs: list[DeviceInfo] = []

    for i, dev in enumerate(devices):
        info = DeviceInfo(
            index=i,
            name=dev["name"],
            hostapi=hostapi_names.get(dev["hostapi"], "unknown"),
            max_input_channels=dev["max_input_channels"],
            max_output_channels=dev["max_output_channels"],
            default_samplerate=dev["default_samplerate"],
            is_default_input=(i == default_input_idx),
            is_default_output=(i == default_output_idx),
        )
        if dev["max_input_channels"] > 0:
            inputs.append(info)
        if dev["max_output_channels"] > 0:
            outputs.append(info)

    return inputs, outputs, default_input_idx, default_output_idx


@router.get("/devices", response_model=DeviceListResponse)
async def list_devices() -> DeviceListResponse:
    """List all available audio input and output devices."""
    inputs, outputs, _, _ = _query_devices()
    return DeviceListResponse(
        input_devices=inputs,
        output_devices=outputs,
        current_input=_audio_state["input_device"],
        current_output=_audio_state["output_device"],
    )


@router.get("/devices/input")
async def get_input_device() -> dict[str, Any]:
    """Get the currently selected input device."""
    return {"device": _audio_state["input_device"], "type": "input"}


@router.get("/devices/output")
async def get_output_device() -> dict[str, Any]:
    """Get the currently selected output device."""
    return {"device": _audio_state["output_device"], "type": "output"}


@router.put("/devices/input")
async def set_input_device(req: DeviceSetRequest) -> dict[str, Any]:
    """
    Set the input (microphone) device.

    Pass device=null to revert to system default.
    Works with both new voice engine and legacy audio pipeline.
    """
    _audio_state["input_device"] = str(req.device) if req.device is not None else None
    log.info("input_device_changed", device=_audio_state["input_device"])

    ve = _audio_state.get("voice_engine")
    if ve is not None and getattr(ve, "is_running", False):
        try:
            capture = getattr(ve, "_modules", {}).get("audio_capture")
            if capture is not None:
                await capture.stop()
                capture._config.input_device = _audio_state["input_device"]
                await capture.start()
                log.info("voice_engine_capture_restarted_with_new_device")
        except Exception as exc:
            log.error("voice_engine_device_switch_failed", error=str(exc))
            return {"device": _audio_state["input_device"], "warning": str(exc)}
    else:
        pipeline = _audio_state.get("audio_pipeline")
        if pipeline is not None:
            try:
                pipeline.stream.stop()
                pipeline.stream.config.input_device = _audio_state["input_device"]
                await pipeline.stream.start()
                log.info("audio_stream_restarted_with_new_device")
            except Exception as exc:
                log.error("audio_stream_restart_failed", error=str(exc))
                return {"device": _audio_state["input_device"], "warning": str(exc)}

    return {"device": _audio_state["input_device"], "status": "ok"}


@router.put("/devices/output")
async def set_output_device(req: DeviceSetRequest) -> dict[str, Any]:
    """
    Set the output (speaker) device.

    Pass device=null to revert to system default.
    """
    import sounddevice as sd  # type: ignore[import-untyped]

    device_val = req.device
    if device_val is not None:
        with contextlib.suppress(TypeError, ValueError):
            device_val = int(device_val)

    _audio_state["output_device"] = str(device_val) if device_val is not None else None

    try:
        current_default = list(sd.default.device)
        current_default[1] = device_val if device_val is not None else -1
        sd.default.device = tuple(current_default)
        log.info("output_device_changed", device=_audio_state["output_device"])
    except Exception as exc:
        log.error("output_device_change_failed", error=str(exc))
        return {"device": _audio_state["output_device"], "warning": str(exc)}

    return {"device": _audio_state["output_device"], "status": "ok"}


@router.get("/voice/status", response_model=VoiceStatusResponse)
async def voice_status() -> VoiceStatusResponse:
    """Get the current voice pipeline status, auto-detecting active mode."""
    ve = _audio_state.get("voice_engine")
    pipeline = _audio_state.get("audio_pipeline")
    tts_mgr = _audio_state.get("tts_manager")

    if ve is not None and getattr(ve, "is_running", False):
        fsm = getattr(ve, "fsm", None)
        modules = list(getattr(ve, "_modules", {}).keys())
        return VoiceStatusResponse(
            voice_mode="full_duplex",
            running=True,
            tts_available=tts_mgr is not None,
            stt_available="streaming_stt" in modules,
            wake_word_available=False,
            current_input_device=_audio_state["input_device"],
            current_output_device=_audio_state["output_device"],
            fsm_state=fsm.state.name if fsm and hasattr(fsm, "state") else None,
            modules_loaded=modules,
        )

    return VoiceStatusResponse(
        voice_mode="legacy",
        running=pipeline is not None and getattr(pipeline, "_running", False),
        tts_available=tts_mgr is not None,
        stt_available=pipeline is not None and hasattr(pipeline, "stt"),
        wake_word_available=pipeline is not None and hasattr(pipeline, "wake_word"),
        current_input_device=_audio_state["input_device"],
        current_output_device=_audio_state["output_device"],
    )


class VoiceSettingsResponse(BaseModel):
    """Current TTS voice and provider settings."""

    voice: str
    provider: str
    available_providers: list[str]


class VoiceSettingsRequest(BaseModel):
    """Request to change voice or provider."""

    voice: str | None = None
    provider: str | None = None


@router.get("/voice/voices")
async def list_voices() -> dict[str, Any]:
    """List available TTS voices grouped by provider."""
    voices: dict[str, list[dict[str, str]]] = {
        "csm": [],
        "xtts_v2": [],
        "kokoro": [],
    }

    tts_mgr = _audio_state.get("tts_manager")
    if tts_mgr:
        for eng in getattr(tts_mgr, "_engine_list", []):
            if not eng._available:
                continue
            if eng.name == "csm":
                voices["csm"].append(
                    {
                        "id": "csm_default",
                        "name": "CSM (Sesame)",
                        "gender": "Any",
                        "locale": "en",
                    }
                )
            elif eng.name == "xtts_v2":
                voices["xtts_v2"].append(
                    {
                        "id": "xtts_v2_default",
                        "name": "XTTS v2 (clone)",
                        "gender": "Any",
                        "locale": "en",
                    }
                )
            elif eng.name == "kokoro":
                kokoro_voice = getattr(eng, "_voice", "af_heart")
                voices["kokoro"].append(
                    {
                        "id": kokoro_voice,
                        "name": kokoro_voice,
                        "gender": "Female",
                        "locale": "en-US",
                    }
                )

    return {
        "voices": voices,
        "current_voice": _audio_state["tts_voice"],
        "current_provider": _audio_state["tts_provider"],
    }


@router.get("/voice/settings", response_model=VoiceSettingsResponse)
async def get_voice_settings() -> VoiceSettingsResponse:
    """Get current voice and provider settings."""
    available: list[str] = []
    tts_mgr = _audio_state.get("tts_manager")
    if tts_mgr:
        for eng in getattr(tts_mgr, "_engine_list", []):
            if eng._available and eng.name not in available:
                available.append(eng.name)

    return VoiceSettingsResponse(
        voice=_audio_state["tts_voice"],
        provider=_audio_state["tts_provider"],
        available_providers=available,
    )


@router.put("/voice/settings")
async def set_voice_settings(req: VoiceSettingsRequest) -> dict[str, Any]:
    """Update the TTS voice and/or provider."""
    if req.provider is not None:
        _audio_state["tts_provider"] = req.provider
        log.info("tts_provider_changed", provider=req.provider)

    if req.voice is not None:
        _audio_state["tts_voice"] = req.voice
        log.info("tts_voice_changed", voice=req.voice)
        # Propagate to live TTS engine
        tts_mgr = _audio_state.get("tts_manager")
        if tts_mgr and hasattr(tts_mgr, "set_voice"):
            tts_mgr.set_voice(req.voice)

    return {
        "voice": _audio_state["tts_voice"],
        "provider": _audio_state["tts_provider"],
        "status": "ok",
    }


class TTSTestRequest(BaseModel):
    """Request body for TTS test."""

    text: str = "Hello! I'm Emily, your AI assistant. Nice to meet you!"
    engine: str | None = None


@router.post("/voice/test-tts")
async def test_tts(req: TTSTestRequest) -> dict[str, str]:
    """Test TTS by speaking a sample sentence through the output device."""
    tts_mgr = _audio_state.get("tts_manager")
    if tts_mgr is None:
        raise HTTPException(503, "TTS not available — voice pipeline not started")

    engine = req.engine or _audio_state.get("tts_provider")

    try:
        from config import get_settings
        from voice.output_stream import AudioOutputStream

        output = AudioOutputStream(output_device=get_settings().audio.output_device)
        chunks = tts_mgr.speak(text=req.text, force_engine=engine)
        await output.play_stream(chunks)
        return {"status": "ok", "text": req.text}
    except Exception as exc:
        log.error("tts_test_failed", error=str(exc))
        raise HTTPException(500, f"TTS test failed: {exc}") from exc
