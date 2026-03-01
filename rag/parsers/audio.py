"""Audio parser — transcribes audio files using Faster-Whisper."""

from __future__ import annotations


def parse(path: str) -> str:
    """
    Transcribe an audio file to text using Faster-Whisper.

    Uses the global STTConfig from config.yaml so model, device, and
    compute_type stay in sync with the rest of the voice pipeline.

    Args:
        path: Path to the audio file (.mp3, .wav, .m4a, etc.).

    Returns:
        Transcribed text.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]

        from config import get_settings

        stt_cfg = get_settings().stt
        model = WhisperModel(
            stt_cfg.model,
            device=stt_cfg.device,
            compute_type=stt_cfg.compute_type,
        )
        segments, info = model.transcribe(
            path,
            beam_size=stt_cfg.beam_size,
            language=stt_cfg.language,
        )
        text = " ".join(s.text.strip() for s in segments)
        return f"[Audio transcription: {info.language}]\n\n{text}"
    except ImportError:
        return "[faster-whisper not installed. Cannot transcribe audio.]"
    except Exception as exc:
        return f"[Audio transcription error: {exc}]"
