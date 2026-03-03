"""
Edge TTS read-aloud endpoint — streams MP3 audio for any text.

Uses Microsoft Edge's neural TTS voices via the edge-tts library.
No API key required; runs entirely over the public Edge speech service.
"""

from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from observability.logger import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/tts", tags=["tts"])

_DEFAULT_VOICE = "en-US-AriaNeural"


class SpeakRequest(BaseModel):
    """Request body for the speak endpoint."""

    text: str = Field(..., min_length=1, max_length=5000)
    voice: str = Field(default=_DEFAULT_VOICE)


@router.post("/speak")
async def speak(req: SpeakRequest) -> StreamingResponse:
    """Synthesize speech from text and return MP3 audio.

    Args:
        req: The text to speak and optional voice override.

    Returns:
        Streaming MP3 audio response.
    """
    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="edge-tts not installed") from exc

    try:
        communicate = edge_tts.Communicate(req.text, req.voice)
        buf = BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])

        buf.seek(0)
        if buf.getbuffer().nbytes == 0:
            raise HTTPException(status_code=500, detail="TTS produced no audio")

        return StreamingResponse(
            buf,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=speech.mp3"},
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("edge_tts_synthesis_failed", error=str(exc)[:200])
        raise HTTPException(status_code=500, detail=f"TTS failed: {exc}") from exc
