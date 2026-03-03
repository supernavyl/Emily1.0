"""Video parser — extracts audio track and transcribes it."""

from __future__ import annotations

import tempfile
from pathlib import Path


def parse(path: str) -> str:
    """
    Transcribe the audio track of a video file.

    Extracts the audio using ffmpeg, then transcribes with Faster-Whisper.

    Args:
        path: Path to the video file.

    Returns:
        Transcribed text.
    """
    import shutil

    if not shutil.which("ffmpeg"):
        return "[ffmpeg not found. Install ffmpeg to process video files.]"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        import subprocess

        result = subprocess.run(
            ["ffmpeg", "-i", path, "-vn", "-ar", "16000", "-ac", "1", "-f", "wav", tmp_path, "-y"],
            capture_output=True,
            timeout=300,
        )
        if result.returncode != 0:
            return f"[ffmpeg extraction failed: {result.stderr.decode(errors='replace')[:200]}]"

        from rag.parsers.audio import parse as audio_parse

        return audio_parse(tmp_path)
    except subprocess.TimeoutExpired:
        return "[Video processing timed out]"
    except Exception as exc:
        return f"[Video parse error: {exc}]"
    finally:
        Path(tmp_path).unlink(missing_ok=True)
