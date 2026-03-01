"""
API routes for voice engine status.

Provides basic visibility into whether the VoiceEngine 1.3 conversation
loop is active.  Detailed provider info comes from the engine's own config.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/voice-engine", tags=["voice-engine"])

_engine_ref: Any = None


def configure_voice_engine_routes(engine: Any = None) -> None:
    """Inject the VoiceConversation instance for status queries."""
    global _engine_ref
    _engine_ref = engine


@router.get("/status")
async def voice_engine_status() -> JSONResponse:
    """Get voice engine status."""
    if _engine_ref is None:
        return JSONResponse({"enabled": False, "status": "not_initialized"})

    state = getattr(_engine_ref, "_state", None)
    return JSONResponse(
        {
            "enabled": True,
            "running": state is not None,
            "state": state.value if state else "unknown",
        }
    )
