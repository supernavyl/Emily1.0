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

import asyncio
import contextlib
import datetime
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

# Strip emoji/symbols so TTS never speaks them aloud
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001ffff"
    "\U00002600-\U000027bf"
    "\U0001fa00-\U0001fa9f"
    "\u2194-\u2199\u2300-\u23ff\u25a0-\u26ff]+",
    re.UNICODE,
)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.settings_store import get_settings_store
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
    # Full pipeline model details
    stt_provider: str | None = None
    stt_model: str | None = None
    llm_tier: str | None = None
    llm_model: str | None = None
    tts_engine: str | None = None
    tts_voice: str | None = None
    vad_threshold: float | None = None
    latency_ms: float | None = None


_audio_state: dict[str, Any] = {
    "input_device": None,
    "output_device": None,
    "audio_pipeline": None,
    "tts_manager": None,
    "voice_engine": None,
    "tts_voice": "af_heart",
    "tts_provider": "kokoro",
    # Managed by start/stop endpoints
    "_listening": False,
    "_fsm_override": None,
    "_listen_task": None,
    "_transcript": [],
    "_last_llm_tier": None,  # updated each LLM call: "voice_fast" | "smart"
    "_last_llm_model": None,  # short model name used in last response
    "emily_llm_provider": None,  # EmilyLLMProvider instance (full brain)
}


def _normalize_device(dev: str | int | None) -> int | None:
    """Convert a string device index (e.g. '40') to int; keep None as None."""
    if dev is None:
        return None
    with contextlib.suppress(TypeError, ValueError):
        return int(dev)
    return None  # non-numeric strings (device names) not supported for index-based lookup


def _resolve_device(spec: str | int | None, direction: str = "input") -> int | None:
    """Resolve a device specification to a sounddevice index.

    Args:
        spec: "auto", an integer index, a device name substring, or None.
        direction: "input" or "output" — used for auto-detection.

    Returns:
        Integer device index, or None if no suitable device found.
    """
    if spec is None:
        return None

    # Integer index — use directly
    if isinstance(spec, int):
        return spec

    spec_str = str(spec).strip()

    # Numeric string — parse as index
    try:
        return int(spec_str)
    except ValueError:
        pass

    # "auto" — use sounddevice default
    if spec_str.lower() == "auto":
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

            defaults = sd.default.device
            idx = defaults[0] if direction == "input" else defaults[1]
            if idx is not None and idx >= 0:
                return int(idx)
            # Fallback: find first device with channels in the right direction
            devices = sd.query_devices()
            for i, d in enumerate(devices):
                channels = (
                    d.get("max_input_channels", 0)
                    if direction == "input"
                    else d.get("max_output_channels", 0)
                )
                if channels > 0:
                    return i
        except Exception:
            pass
        return None

    # Device name substring match
    try:
        import sounddevice as sd  # type: ignore[import-untyped]

        devices = sd.query_devices()
        spec_lower = spec_str.lower()
        for i, d in enumerate(devices):
            if spec_lower in d.get("name", "").lower():
                channels = (
                    d.get("max_input_channels", 0)
                    if direction == "input"
                    else d.get("max_output_channels", 0)
                )
                if channels > 0:
                    return i
    except Exception:
        pass

    return None


def set_audio_state(
    *,
    input_device: str | int | None = None,
    output_device: str | int | None = None,
    audio_pipeline: Any = None,
    tts_manager: Any = None,
    voice_engine: Any = None,
    emily_llm: Any = None,
) -> None:
    """Inject runtime audio state from app lifespan or bootstrap."""
    if input_device is not None:
        resolved = _resolve_device(input_device, "input")
        _audio_state["input_device"] = resolved
        log.info("audio_input_resolved", spec=input_device, resolved=resolved)
    if output_device is not None:
        resolved = _resolve_device(output_device, "output")
        _audio_state["output_device"] = resolved
        log.info("audio_output_resolved", spec=output_device, resolved=resolved)
        # Sync sd.default.device so Speaker(device=None) immediately uses this device
        try:
            import sounddevice as sd  # type: ignore[import-untyped]

            current = list(sd.default.device)
            current[1] = resolved if resolved is not None else -1
            sd.default.device = tuple(current)
        except Exception:
            pass
    if audio_pipeline is not None:
        _audio_state["audio_pipeline"] = audio_pipeline
    if tts_manager is not None:
        _audio_state["tts_manager"] = tts_manager
    # voice_engine kept for backward compat but not required
    if voice_engine is not None:
        _audio_state["voice_engine"] = voice_engine
    if emily_llm is not None:
        _audio_state["emily_llm_provider"] = emily_llm


def _persist_audio_device(env_key: str, value: int | None) -> None:
    """Write an audio device selection to .env so it survives restarts."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    try:
        lines = env_path.read_text().splitlines() if env_path.exists() else []
    except OSError:
        lines = []

    prefix = f"{env_key}="
    new_line = f"{env_key}={value}" if value is not None else f"# {env_key}="
    updated = [
        new_line if line.startswith(prefix) or line.startswith(f"# {prefix}") else line
        for line in lines
    ]
    if not any(line.startswith(prefix) or line.startswith(f"# {prefix}") for line in lines):
        updated.append(new_line)

    try:
        env_path.write_text("\n".join(updated) + "\n")
        log.info("audio_device_persisted", key=env_key, value=value)
    except OSError as exc:
        log.warning("audio_device_persist_failed", error=str(exc))


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
    inp = _audio_state["input_device"]
    out = _audio_state["output_device"]
    return DeviceListResponse(
        input_devices=inputs,
        output_devices=outputs,
        current_input=str(inp) if inp is not None else None,
        current_output=str(out) if out is not None else None,  # frontend expects str
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
    dev = req.device
    if dev is not None:
        with contextlib.suppress(TypeError, ValueError):
            dev = int(dev)
    _audio_state["input_device"] = dev  # int | None
    _persist_audio_device("EMILY_AUDIO__INPUT_DEVICE", dev if isinstance(dev, int) else None)
    get_settings_store().update_section("audio", {"input_device": dev})
    log.info("input_device_changed", device=dev)

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
    Persists to .env so the choice survives restarts.
    """
    import sounddevice as sd  # type: ignore[import-untyped]

    device_val = req.device
    if device_val is not None:
        with contextlib.suppress(TypeError, ValueError):
            device_val = int(device_val)

    # Store as int internally so sounddevice always receives a proper index
    _audio_state["output_device"] = device_val  # int | None

    try:
        current_default = list(sd.default.device)
        current_default[1] = device_val if device_val is not None else -1
        sd.default.device = tuple(current_default)
        log.info("output_device_changed", device=device_val)
    except Exception as exc:
        log.error("output_device_change_failed", error=str(exc))
        return {"device": device_val, "warning": str(exc)}

    # Persist to .env so the selection survives API restarts
    # Key follows EmilySettings env_prefix="EMILY_" + env_nested_delimiter="__"
    _persist_audio_device("EMILY_AUDIO__OUTPUT_DEVICE", device_val)
    get_settings_store().update_section("audio", {"output_device": device_val})

    return {"device": device_val, "status": "ok"}


def _pipeline_model_info() -> dict:
    """Read pipeline model names from VoiceEngineConfig and Emily config."""
    stt_prov = "faster_whisper"
    stt_mdl = "base.en"
    vad_thr: float | None = 0.5
    try:
        from voice_engine.config import VoiceEngineConfig

        ve_cfg = VoiceEngineConfig()
        stt_prov = ve_cfg.stt_provider
        stt_mdl = ve_cfg.stt_model
        vad_thr = ve_cfg.vad_threshold
    except Exception:
        pass

    # LLM: prefer last-used tier/model (updated each response); fall back to config default
    llm_tier = _audio_state.get("_last_llm_tier") or "voice_fast"
    llm_mdl: str | None = _audio_state.get("_last_llm_model")
    if not llm_mdl:
        try:
            from config import get_settings

            llm_mdl = get_settings().llm.models.voice_fast
        except Exception:
            pass

    return {
        "stt_provider": stt_prov,
        "stt_model": stt_mdl,
        "llm_tier": llm_tier,
        "llm_model": llm_mdl,
        "tts_engine": _audio_state.get("tts_provider", "kokoro"),
        "tts_voice": _audio_state.get("tts_voice", "af_heart"),
        "vad_threshold": vad_thr,
    }


@router.get("/voice/status", response_model=VoiceStatusResponse)
async def voice_status() -> VoiceStatusResponse:
    """Get the current voice pipeline status, auto-detecting active mode."""
    ve = _audio_state.get("voice_engine")
    pipeline = _audio_state.get("audio_pipeline")
    tts_mgr = _audio_state.get("tts_manager")
    pipeline_info = _pipeline_model_info()

    if ve is not None and getattr(ve, "is_running", False):
        fsm = getattr(ve, "fsm", None)
        modules = list(getattr(ve, "_modules", {}).keys())
        return VoiceStatusResponse(
            voice_mode="full_duplex",
            running=True,
            tts_available=tts_mgr is not None,
            stt_available="streaming_stt" in modules,
            wake_word_available=False,
            current_input_device=str(_audio_state["input_device"])
            if _audio_state["input_device"] is not None
            else None,
            current_output_device=str(_audio_state["output_device"])
            if _audio_state["output_device"] is not None
            else None,
            fsm_state=fsm.state.name if fsm and hasattr(fsm, "state") else None,
            modules_loaded=modules,
            **pipeline_info,
        )

    pipeline_running = pipeline is not None and getattr(pipeline, "_running", False)
    api_listening = _audio_state["_listening"]
    return VoiceStatusResponse(
        voice_mode="legacy",
        running=pipeline_running or api_listening,
        tts_available=tts_mgr is not None,
        stt_available=pipeline is not None and hasattr(pipeline, "stt"),
        wake_word_available=pipeline is not None and hasattr(pipeline, "wake_word"),
        current_input_device=str(_audio_state["input_device"]),
        current_output_device=str(_audio_state["output_device"]),
        fsm_state=_audio_state["_fsm_override"] or ("LISTENING" if api_listening else None),
        **pipeline_info,
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
        from voice.output_stream import AudioOutputStream

        output = AudioOutputStream(output_device=_audio_state.get("output_device"))
        clean_text = _EMOJI_RE.sub("", req.text).strip() or req.text
        chunks = tts_mgr.speak(text=clean_text, force_engine=engine)
        await output.play_stream(chunks)
        return {"status": "ok", "text": clean_text}
    except Exception as exc:
        log.error("tts_test_failed", error=str(exc))
        raise HTTPException(500, f"TTS test failed: {exc}") from exc


# ── Voice start / stop ──────────────────────────────────────────────────────


class _VoiceEngineUI:
    """Drop-in for TerminalUI: routes VoiceConversation events into _audio_state."""

    def _append(self, event: str, text: str) -> None:
        entry = {
            "event": event,
            "text": text,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
        _audio_state["_transcript"].append(entry)
        if len(_audio_state["_transcript"]) > 50:
            _audio_state["_transcript"] = _audio_state["_transcript"][-50:]

    def show_welcome(self) -> None:
        log.info("voice_engine_started")

    def show_status(self, msg: str) -> None:
        log.info("voice_engine_status", msg=msg)

    def show_listening(self) -> None:
        _audio_state["_fsm_override"] = "LISTENING"

    def show_processing(self) -> None:
        _audio_state["_fsm_override"] = "PROCESSING"

    def show_transcript(self, text: str) -> None:
        self._append("stt_result", text)
        log.info("stt_result", text=text)

    def show_response(self, text: str) -> None:
        _audio_state["_fsm_override"] = "SPEAKING"
        t = _audio_state["_transcript"]
        if t and t[-1]["event"] == "tts_speak":
            # Same response turn — append sentence rather than creating a new entry
            t[-1]["text"] = t[-1]["text"].rstrip() + " " + text.strip()
        else:
            t.append(
                {
                    "event": "tts_speak",
                    "text": text,
                    "timestamp": datetime.datetime.utcnow().isoformat(),
                }
            )
            if len(t) > 50:
                _audio_state["_transcript"] = t[-50:]
        log.info("tts_response", text=text[:80])

    def show_error(self, msg: str) -> None:
        log.error("voice_engine_error", error=msg)

    def show_goodbye(self) -> None:
        log.info("voice_engine_stopped")


_VOICE_SYSTEM_PROMPT = (
    "You are Emily, a warm, witty, and intelligent voice assistant. "
    "Respond naturally as if in a real-time spoken conversation. "
    "Keep answers concise — one to three sentences — unless the user asks for more detail. "
    "Never use markdown, bullet points, numbered lists, asterisks, or emojis. "
    "Write only plain spoken sentences because your output will be read aloud by TTS. "
    "If you don't know something, say so briefly rather than speculating."
)


class _EmilyLLMBridge:
    """Streams LLM responses via direct Ollama call — same path as terminal mode.

    Uses the voice_fast model from config.yaml (8B JOSIEFIED-Qwen3) with
    think=False so there is no reasoning delay before the first spoken token.
    Falls back to sensible defaults if config is unavailable.
    """

    def __init__(self) -> None:
        try:
            from config import get_settings

            cfg = get_settings()
            self._model = cfg.llm.models.voice_fast
            self._base_url = cfg.llm.ollama_base_url
        except Exception:
            self._model = "goekdenizguelmez/JOSIEFIED-Qwen3:8b"
            self._base_url = "http://localhost:11434"
        log.info("voice_llm_bridge_ready", model=self._model, base_url=self._base_url)

    async def stream_response(
        self,
        messages: list[dict[str, str]],
        system: str,
    ) -> AsyncIterator[str]:
        from ollama import AsyncClient

        _audio_state["_last_llm_tier"] = "voice_fast"
        _audio_state["_last_llm_model"] = self._model

        full_messages: list[dict[str, str]] = [
            {"role": "system", "content": system or _VOICE_SYSTEM_PROMPT},
        ]
        full_messages.extend(messages)

        from voice_engine.processing.think_filter import strip_think_tags

        client = AsyncClient(host=self._base_url)

        async def _raw_stream() -> AsyncIterator[str]:
            stream = await client.chat(
                model=self._model,
                messages=full_messages,
                stream=True,
                think=False,  # Disable Qwen3 extended thinking
                options={"temperature": 0.7, "num_predict": 800},
            )
            async for chunk in stream:
                msg = getattr(chunk, "message", None)
                content: str = (
                    getattr(msg, "content", "") or ""
                    if msg is not None
                    else chunk.get("message", {}).get("content", "")  # type: ignore[union-attr]
                    if isinstance(chunk, dict)
                    else ""
                )
                if content:
                    yield content

        try:
            async for token in strip_think_tags(_raw_stream()):
                clean = _EMOJI_RE.sub("", token)
                if clean:
                    yield clean
        except Exception as exc:
            log.error("voice_llm_error", model=self._model, error=str(exc))


async def _voice_engine_loop() -> None:
    """Background task: runs VoiceConversation (mic → VAD → STT → LLM → TTS).

    Replaces the manual _stt_listen_loop. VoiceConversation handles:
    - Native-rate mic capture with auto-resample to 16 kHz for Silero/Whisper
    - Exact 512-sample Silero VAD windowing
    - Barge-in interruption while Emily is speaking
    """
    import asyncio

    from voice_engine.config import VoiceEngineConfig
    from voice_engine.conversation import VoiceConversation

    input_dev = str(_audio_state.get("input_device") or "")
    # Pass empty string for output — Speaker uses sd.default.device (kept in sync by
    # set_audio_state / set_output_device), so device changes take effect immediately
    # even mid-session without restarting the conversation.
    ve_config = VoiceEngineConfig(
        audio_input_device=input_dev,
        audio_output_device="",
    )

    tts_mgr = _audio_state.get("tts_manager")
    emily_tts = None
    if tts_mgr is not None:
        from voice_engine.providers.tts.emily_tts import EmilyTTSProvider

        emily_tts = EmilyTTSProvider(tts_manager=tts_mgr)

    # Prefer EmilyLLMProvider (full brain: memory, RAG, persona, complexity routing)
    # injected by bootstrap. Fall back to bare _EmilyLLMBridge for standalone API use.
    llm_provider = _audio_state.get("emily_llm_provider") or _EmilyLLMBridge()
    conv = VoiceConversation(ve_config, llm=llm_provider, tts=emily_tts)
    conv._ui = _VoiceEngineUI()  # type: ignore[assignment]

    output_dev = str(_audio_state.get("output_device") or "")
    _audio_state["_fsm_override"] = "LOADING"
    log.info("voice_engine_loop_starting", input_dev=input_dev, output_dev=output_dev)
    try:
        await conv.run()
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        log.error("voice_engine_loop_error", error=str(exc))
        try:
            from observability.metrics import STT_ERRORS_TOTAL

            STT_ERRORS_TOTAL.inc()
        except Exception:
            pass
    finally:
        _audio_state["_listening"] = False
        _audio_state["_fsm_override"] = None
        _audio_state["_listen_task"] = None
        log.info("voice_engine_loop_stopped")


_voice_lock = asyncio.Lock()


@router.post("/voice/start")
async def voice_start() -> dict[str, str]:
    """Start the voice listening pipeline (STT → LLM → TTS loop)."""
    async with _voice_lock:
        if _audio_state["_listening"]:
            return {"status": "already_running"}

        _audio_state["_listening"] = True
        task = asyncio.create_task(_voice_engine_loop())
        _audio_state["_listen_task"] = task
    return {"status": "started"}


@router.post("/voice/stop")
async def voice_stop() -> dict[str, str]:
    """Stop the voice listening pipeline."""
    async with _voice_lock:
        _audio_state["_listening"] = False
        task = _audio_state.get("_listen_task")
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        _audio_state["_listen_task"] = None
        _audio_state["_fsm_override"] = None
    return {"status": "stopped"}


@router.get("/voice/transcript")
async def get_voice_transcript() -> dict[str, Any]:
    """Return buffered voice transcript entries."""
    return {"entries": _audio_state.get("_transcript", [])}
