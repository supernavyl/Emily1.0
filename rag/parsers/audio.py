"""Audio parser — transcribes audio files using Faster-Whisper."""

from __future__ import annotations


def parse(path: str) -> str:
    """
    Transcribe an audio file to text using Faster-Whisper.

    Args:
        path: Path to the audio file (.mp3, .wav, .m4a, etc.).

    Returns:
        Transcribed text.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        model = WhisperModel("large-v3", device="cuda", compute_type="float16")
        segments, info = model.transcribe(path, beam_size=5)
        text = " ".join(s.text.strip() for s in segments)
        return f"[Audio transcription: {info.language}]\n\n{text}"
    except ImportError:
        return "[faster-whisper not installed. Cannot transcribe audio.]"
    except Exception as exc:
        return f"[Audio transcription error: {exc}]"
