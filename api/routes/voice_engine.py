"""
API routes for Emily's voice engine status and control.

Provides real-time visibility into:
- Conversation FSM state
- Turn detection signal breakdown
- Emotion detection
- Backchannel/filler/interrupt counts
- Latency budget status
- Rhythm synchronization profile
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/voice-engine", tags=["voice-engine"])

_engine_ref: Any = None
_fsm_ref: Any = None
_latency_ref: Any = None


def configure_voice_engine_routes(
    engine: Any = None,
    fsm: Any = None,
    latency_budget: Any = None,
) -> None:
    """
    Inject module references for the API routes.

    Args:
        engine: VoiceEngine instance.
        fsm: ConversationFSM instance.
        latency_budget: LatencyBudget instance.
    """
    global _engine_ref, _fsm_ref, _latency_ref
    _engine_ref = engine
    _fsm_ref = fsm
    _latency_ref = latency_budget


@router.get("/status")
async def voice_engine_status() -> JSONResponse:
    """
    Get the current voice engine status.

    Returns:
        JSON with FSM state, module availability, and running status.
    """
    if _engine_ref is None:
        return JSONResponse({"enabled": False, "status": "not_initialized"})

    fsm = _engine_ref.fsm if _engine_ref else None
    state = fsm.state.name if fsm else "unknown"
    state_duration = fsm.state_duration_s if fsm else 0

    return JSONResponse({
        "enabled": True,
        "running": _engine_ref.is_running,
        "fsm_state": state,
        "state_duration_s": round(state_duration, 2),
    })


@router.get("/turn-signal")
async def turn_signal() -> JSONResponse:
    """
    Get the latest turn detection signal with per-signal breakdown.

    Returns:
        JSON with score, action, and confidence breakdown.
    """
    if _fsm_ref is None:
        return JSONResponse({"available": False})

    turn_detector = getattr(_fsm_ref, "_turn_detector", None)
    if turn_detector is None:
        return JSONResponse({"available": False})

    signal = turn_detector.last_signal
    if signal is None:
        return JSONResponse({"available": True, "signal": None})

    return JSONResponse({
        "available": True,
        "signal": {
            "score": round(signal.score, 3),
            "action": signal.action.name,
            "breakdown": {k: round(v, 3) for k, v in signal.confidence_breakdown.items()},
        },
    })


@router.get("/emotion")
async def emotion_state() -> JSONResponse:
    """
    Get the current detected user emotion.

    Returns:
        JSON with emotion, confidence, valence, arousal, cognitive load.
    """
    if _fsm_ref is None:
        return JSONResponse({"available": False})

    emotion = getattr(_fsm_ref, "_current_emotion", None)
    if emotion is None:
        return JSONResponse({"available": True, "emotion": None})

    return JSONResponse({
        "available": True,
        "emotion": {
            "primary": emotion.primary.value,
            "confidence": round(emotion.confidence, 3),
            "valence": round(emotion.valence, 3),
            "arousal": round(emotion.arousal, 3),
            "cognitive_load": round(emotion.cognitive_load, 3),
            "engagement": round(emotion.engagement, 3),
        },
    })


@router.get("/rhythm")
async def rhythm_profile() -> JSONResponse:
    """
    Get the current rhythm synchronization state.

    Returns:
        JSON with user rhythm profile and Emily's target parameters.
    """
    if _fsm_ref is None:
        return JSONResponse({"available": False})

    rhythm = getattr(_fsm_ref, "_rhythm_sync", None)
    if rhythm is None:
        return JSONResponse({"available": False})

    targets = rhythm.get_targets()
    profile = rhythm.user_profile

    return JSONResponse({
        "available": True,
        "user_profile": {
            "speaking_rate_syl_s": round(profile.speaking_rate_syl_s, 2),
            "pause_duration_ms": round(profile.pause_duration_ms, 1),
            "response_latency_ms": round(profile.response_latency_ms, 1),
        },
        "emily_targets": {
            "speaking_rate_syl_s": round(targets.speaking_rate_syl_s, 2),
            "pause_duration_ms": round(targets.pause_duration_ms, 1),
            "phrase_length_words": targets.phrase_length_words,
            "response_latency_ms": round(targets.response_latency_ms, 1),
        },
        "entrainment_degree": rhythm.entrainment_degree,
    })


@router.get("/latency")
async def latency_report() -> JSONResponse:
    """
    Get latency budget report with P50/P95/P99 per stage.

    Returns:
        JSON with per-stage latency percentiles.
    """
    if _latency_ref is None:
        return JSONResponse({"available": False})

    report = _latency_ref.report()
    return JSONResponse({
        "available": True,
        "stages": report,
    })


@router.get("/stats")
async def voice_engine_stats() -> JSONResponse:
    """
    Get aggregate voice engine statistics.

    Returns:
        JSON with backchannel count, interrupt count, filler count, etc.
    """
    if _fsm_ref is None:
        return JSONResponse({"available": False})

    stats: dict[str, Any] = {}

    bc = getattr(_fsm_ref, "_backchannel_engine", None)
    if bc:
        stats["backchannels_generated"] = bc.session_count

    interrupt = getattr(_fsm_ref, "_interrupt_handler", None)
    if interrupt:
        stats["interrupts_handled"] = interrupt.interrupt_count

    from llm.speculative import SpeculativeCache
    stats["speculative_cache"] = {"hits": 0, "misses": 0, "hit_rate": 0.0}

    return JSONResponse({"available": True, "stats": stats})


@router.get("/pipeline-status")
async def pipeline_status() -> JSONResponse:
    """
    Get detailed per-module status for every voice pipeline component.

    Returns:
        JSON with health and config for AEC, noise suppression,
        speaker tracking, streaming STT, VAD, wake word, TTS, and capture.
    """
    if _engine_ref is None:
        return JSONResponse({"available": False})

    modules = getattr(_engine_ref, "_modules", {})
    result: dict[str, Any] = {"available": True, "modules": {}}

    capture = modules.get("audio_capture")
    if capture is not None:
        cfg = getattr(capture, "_config", None)
        result["modules"]["audio_capture"] = {
            "loaded": True,
            "input_sample_rate": getattr(cfg, "input_sample_rate", None),
            "output_sample_rate": getattr(cfg, "output_sample_rate", None),
            "chunk_ms": getattr(cfg, "input_chunk_ms", None),
        }

    aec = modules.get("aec")
    if aec is not None:
        cfg = getattr(aec, "_config", None)
        result["modules"]["aec"] = {
            "loaded": True,
            "tail_length_ms": getattr(cfg, "tail_length_ms", None),
            "sample_rate": getattr(cfg, "sample_rate", None),
        }

    noise = modules.get("noise_suppress")
    if noise is not None:
        snr_mon = getattr(noise, "_snr_monitor", None)
        result["modules"]["noise_suppress"] = {
            "loaded": True,
            "current_snr_db": round(snr_mon.current_snr_db, 1) if snr_mon and hasattr(snr_mon, "current_snr_db") else None,
            "mode": getattr(noise, "_active_mode", "unknown"),
        }

    stt = modules.get("streaming_stt")
    if stt is not None:
        result["modules"]["streaming_stt"] = {
            "loaded": True,
            "model": getattr(stt, "_model_name", None),
            "partial_text": getattr(stt, "_current_partial", None),
        }

    speaker = modules.get("speaker_engine")
    if speaker is not None:
        result["modules"]["speaker_engine"] = {
            "loaded": True,
            "max_speakers": getattr(speaker, "_max_speakers", None),
            "active_count": len(getattr(speaker, "_active_speakers", [])),
        }

    for name in modules:
        if name not in result["modules"]:
            result["modules"][name] = {"loaded": True}

    return JSONResponse(result)


@router.get("/speaker")
async def speaker_info() -> JSONResponse:
    """
    Get current speaker identification and diarization data.

    Returns:
        JSON with active speakers, their IDs, and confidence scores.
    """
    if _engine_ref is None:
        return JSONResponse({"available": False})

    modules = getattr(_engine_ref, "_modules", {})
    speaker_engine = modules.get("speaker_engine")
    if speaker_engine is None:
        return JSONResponse({"available": False})

    active = getattr(speaker_engine, "_active_speakers", [])
    speakers: list[dict[str, Any]] = []
    for s in active:
        speakers.append({
            "speaker_id": getattr(s, "speaker_id", None),
            "label": getattr(s, "label", None),
            "confidence": round(getattr(s, "confidence", 0.0), 3),
            "is_primary": getattr(s, "is_primary", False),
        })

    return JSONResponse({
        "available": True,
        "speakers": speakers,
        "total_tracked": len(speakers),
    })
