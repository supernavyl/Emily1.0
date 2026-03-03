"""
Singing / music generation API routes.

Exposes:
  GET  /api/v1/singing/status    — engine availability
  POST /api/v1/singing/generate  — stream WAV audio from a prompt
"""

from __future__ import annotations

import io
import struct
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from observability.logger import get_logger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from voice.singing import SingingManager

log = get_logger(__name__)

router = APIRouter(prefix="/api/v1/singing", tags=["singing"])

_singing_manager: SingingManager | None = None


def configure(singing_manager: Any) -> None:
    """Inject SingingManager at startup (called from Bootstrap or lifespan)."""
    global _singing_manager
    _singing_manager = singing_manager


def _wav_header_for_streaming(
    sample_rate: int = 24_000,
    channels: int = 1,
    bits: int = 16,
) -> bytes:
    """Build a WAV header with max-size placeholders for streaming.

    Most audio players handle 0xFFFFFFFF data-chunk sizes fine and will play
    the stream until EOF rather than seeking to a known end position.
    """
    buf = io.BytesIO()
    data_size = 0xFFFFFFFF
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 0xFFFFFFFF))  # capped — streaming placeholder
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))
    buf.write(struct.pack("<H", 1))  # PCM format tag
    buf.write(struct.pack("<H", channels))
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * channels * bits // 8))
    buf.write(struct.pack("<H", channels * bits // 8))
    buf.write(struct.pack("<H", bits))
    buf.write(b"data")
    buf.write(struct.pack("<I", data_size))
    return buf.getvalue()


class SingRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    style: str | None = Field(default=None, description="Music style hint, e.g. 'lo-fi jazz'")
    duration_seconds: int = Field(default=30, ge=5, le=120)
    mode: str | None = Field(
        default=None,
        description="generate | voice_convert | full_song | None (auto-select)",
    )


@router.get("/status")
async def singing_status() -> JSONResponse:
    """Return availability of each configured singing engine."""
    if _singing_manager is None:
        return JSONResponse(
            {
                "available": False,
                "engines": [],
                "reason": "SingingManager not initialised",
            }
        )
    engines = [
        {"name": eng.name, "available": eng.available}
        for eng in _singing_manager._engine_list  # noqa: SLF001
    ]
    return JSONResponse({"available": any(e["available"] for e in engines), "engines": engines})


@router.post("/generate")
async def generate_song(req: SingRequest) -> StreamingResponse:
    """Generate and stream a song / music clip for the given prompt.

    Response is a streaming audio/wav at 24 kHz, 16-bit mono PCM.
    The WAV header is sent first so audio players can begin decoding immediately.
    """
    if _singing_manager is None:
        raise HTTPException(status_code=503, detail="SingingManager not initialised")

    async def _stream() -> AsyncIterator[bytes]:
        yield _wav_header_for_streaming()
        try:
            async for chunk in _singing_manager.sing(  # type: ignore[union-attr]
                req.prompt,
                style=req.style,
                duration_seconds=req.duration_seconds,
                mode=req.mode,
            ):
                yield chunk
        except RuntimeError as exc:
            # Can't raise HTTPException inside a running generator; log and stop.
            log.error("singing_api_stream_failed", error=str(exc)[:200])

    return StreamingResponse(
        _stream(),
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="emily_song.wav"'},
    )
