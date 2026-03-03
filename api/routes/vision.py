"""
Vision perception API — live screen capture, webcam, and analysis.

GET  /vision/status       — pipeline state and capabilities
GET  /vision/screenshot   — capture fresh screenshot (raw PNG)
GET  /vision/webcam       — capture fresh webcam frame (raw JPEG)
GET  /vision/observations — cached analysis, presence, emotions, OCR
POST /vision/analyze      — trigger on-demand full analysis
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/vision", tags=["vision"])

# ── Shared state (mirrors _audio_state pattern) ──────────────────────────────

_vision_state: dict[str, Any] = {
    "screen_capture": None,
    "webcam_capture": None,
    "presence": None,
    "analyzer": None,
    "initialized": False,
    # Cached analysis
    "last_screen_analysis": None,
    "last_presence": None,
    "last_emotions": None,
    "last_ocr_text": None,
    "last_analysis_ts": 0.0,
}

_analysis_lock = asyncio.Lock()


# ── Init / cleanup (called from api/app.py lifespan) ─────────────────────────


async def init_vision(config: Any, ollama_url: str = "http://localhost:11434") -> None:
    """Initialize vision subsystem — screen capture, webcam, presence, analyzer."""
    from perception.vision.presence import PresenceDetector
    from perception.vision.screen_capture import ScreenCapture
    from perception.vision.vision_llm import VisionAnalyzer
    from perception.vision.webcam import WebcamCapture

    try:
        sc = ScreenCapture(config)
        wc = WebcamCapture(config)
        await sc.init()
        await wc.init()
        _vision_state["screen_capture"] = sc
        _vision_state["webcam_capture"] = wc
        _vision_state["presence"] = PresenceDetector(
            idle_threshold_s=getattr(config, "presence_idle_threshold_s", 120.0),
        )
        _vision_state["analyzer"] = VisionAnalyzer(
            ollama_url=ollama_url,
            vision_model="minicpm-v:latest",
        )
        _vision_state["initialized"] = True
        log.info(
            "vision_initialized",
            screen=sc._available,
            webcam=wc.is_available,
        )
    except Exception as exc:
        log.warning("vision_init_failed", error=str(exc)[:200])


async def cleanup_vision() -> None:
    """Release vision resources."""
    sc = _vision_state.get("screen_capture")
    wc = _vision_state.get("webcam_capture")
    if sc:
        sc.close()
    if wc:
        wc.release()
    _vision_state["initialized"] = False
    log.info("vision_cleaned_up")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/status")
async def vision_status() -> JSONResponse:
    """Get current vision subsystem status."""
    sc = _vision_state.get("screen_capture")
    wc = _vision_state.get("webcam_capture")
    return JSONResponse(
        {
            "initialized": _vision_state["initialized"],
            "screen_available": bool(sc and getattr(sc, "_available", False)),
            "webcam_available": bool(wc and getattr(wc, "is_available", False)),
            "analyzer_model": "minicpm-v:latest",
            "last_analysis_ts": _vision_state["last_analysis_ts"],
        }
    )


@router.get("/screenshot")
async def get_screenshot() -> Response:
    """Capture a fresh screenshot and return as raw PNG."""
    sc = _vision_state.get("screen_capture")
    if not sc or not getattr(sc, "_available", False):
        raise HTTPException(503, "Screen capture not available")

    b64 = await sc.capture_once()
    if not b64:
        raise HTTPException(500, "Screenshot capture failed")

    png_bytes = base64.b64decode(b64)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/webcam")
async def get_webcam() -> Response:
    """Capture a fresh webcam frame and return as raw JPEG."""
    wc = _vision_state.get("webcam_capture")
    if not wc or not getattr(wc, "is_available", False):
        raise HTTPException(503, "Webcam not available")

    b64, meta = await wc.capture_frame()
    if not b64:
        raise HTTPException(500, "Webcam capture failed")

    # Cache emotion data if present
    if "emotions" in meta:
        _vision_state["last_emotions"] = meta["emotions"]

    jpg_bytes = base64.b64decode(b64)
    return Response(
        content=jpg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/observations")
async def get_observations() -> JSONResponse:
    """Return all cached observation data."""
    # If analysis is stale (>30s) and screen is available, refresh in background
    sc = _vision_state.get("screen_capture")
    age = time.time() - _vision_state["last_analysis_ts"]
    if age > 30 and sc and getattr(sc, "_available", False):
        asyncio.create_task(_background_analyze())

    presence_data = _vision_state.get("last_presence")
    return JSONResponse(
        {
            "screen": _vision_state.get("last_screen_analysis"),
            "presence": presence_data,
            "emotions": _vision_state.get("last_emotions"),
            "ocr_text": _vision_state.get("last_ocr_text"),
            "last_analysis_ts": _vision_state["last_analysis_ts"],
        }
    )


@router.post("/analyze")
async def analyze_now() -> JSONResponse:
    """Trigger on-demand full analysis — screenshot + vision model + OCR + presence."""
    sc = _vision_state.get("screen_capture")
    analyzer = _vision_state.get("analyzer")

    if not sc or not getattr(sc, "_available", False):
        raise HTTPException(503, "Screen capture not available")
    if not analyzer:
        raise HTTPException(503, "Vision analyzer not available")

    async with _analysis_lock:
        try:
            b64 = await sc.capture_once()
            if not b64:
                raise HTTPException(500, "Screenshot capture failed")

            # Run analysis and OCR in parallel
            analysis_task = asyncio.create_task(analyzer.analyze_screen(b64))
            ocr_task = asyncio.create_task(analyzer.extract_text(b64))

            # Update presence
            presence_detector = _vision_state.get("presence")
            if presence_detector:
                try:
                    presence_info = await presence_detector.update(frame=None)
                    _vision_state["last_presence"] = {
                        "state": presence_info.state.value,
                        "face_detected": presence_info.face_detected,
                        "system_idle_s": presence_info.system_idle_s,
                        "confidence": presence_info.confidence,
                    }
                except Exception:
                    pass

            analysis = await analysis_task
            ocr_text = await ocr_task

            _vision_state["last_screen_analysis"] = analysis
            _vision_state["last_ocr_text"] = ocr_text
            _vision_state["last_analysis_ts"] = time.time()

            log.info("vision_analysis_complete", summary=str(analysis.get("summary", ""))[:80])

        except HTTPException:
            raise
        except Exception as exc:
            log.error("vision_analyze_failed", error=str(exc)[:200])
            raise HTTPException(500, f"Analysis failed: {exc}") from exc

    return JSONResponse(
        {
            "screen": _vision_state["last_screen_analysis"],
            "presence": _vision_state.get("last_presence"),
            "emotions": _vision_state.get("last_emotions"),
            "ocr_text": _vision_state["last_ocr_text"],
            "last_analysis_ts": _vision_state["last_analysis_ts"],
        }
    )


async def _background_analyze() -> None:
    """Run analysis in background without blocking the request."""
    if _analysis_lock.locked():
        return  # Already running
    try:
        async with _analysis_lock:
            sc = _vision_state.get("screen_capture")
            analyzer = _vision_state.get("analyzer")
            if not sc or not analyzer:
                return

            b64 = await sc.capture_once()
            if not b64:
                return

            analysis = await analyzer.analyze_screen(b64)
            _vision_state["last_screen_analysis"] = analysis
            _vision_state["last_analysis_ts"] = time.time()
    except Exception as exc:
        log.debug("background_analyze_failed", error=str(exc)[:100])
