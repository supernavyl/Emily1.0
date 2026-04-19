"""Voice Engine configuration via environment variables and .env file."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from observability.logger import get_logger

logger = get_logger(__name__)


def _get_default_system_prompt() -> str:
    """Delegate to prompt_builder — the single source of truth for all prompts."""
    try:
        from llm.prompt_builder import PromptBuilder

        return PromptBuilder().build_voice_system_prompt()
    except Exception:
        # Fallback only if prompt_builder is unavailable (standalone mode)
        return (
            "You are Emily, an AI. Your output is spoken aloud through a voice engine. "
            "Think for yourself. Form your own opinions. Be direct and honest. "
            "Match your depth to the question — don't over-explain simple things. "
            "No emojis, markdown, bullet points, or formatting. Write only speakable words."
        )


class VoiceEngineConfig(BaseSettings):
    """Central configuration loaded from environment / .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── API Keys ──────────────────────────────────
    openai_api_key: str = Field(default="", description="OpenAI API key")
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    google_api_key: str = Field(default="", description="Google AI API key")
    groq_api_key: str = Field(default="", description="Groq API key")
    deepgram_api_key: str = Field(default="", description="Deepgram API key")
    tabby_api_key: str = Field(default="", description="TabbyAPI admin key (optional)")

    # ── STT ────────────────────────────────────────
    stt_provider: str = Field(default="faster_whisper", description="STT provider name")
    stt_model: str = Field(default="distil-large-v3", description="STT model identifier")
    stt_device: str = Field(default="cuda", description="STT device: 'cuda' or 'cpu'")
    stt_device_index: int = Field(
        default=1,
        description="CUDA device index: 0=4090 (with voice LLM), 1=3060 (with embedding+TTS)",
    )
    stt_compute_type: str = Field(
        default="int8", description="STT compute type: int8 on 3060 frees VRAM for TTS"
    )

    # ── LLM ────────────────────────────────────────
    llm_provider: str = Field(default="ollama", description="LLM provider name")
    llm_model: str = Field(default="llama3.2", description="LLM model identifier")
    llm_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for OpenAI-compatible APIs",
    )

    # ── TTS (Orpheus primary, Kokoro fallback) ────
    tts_provider: str = Field(default="orpheus", description="TTS provider: 'orpheus' or 'kokoro'")
    tts_fallback: str = Field(
        default="kokoro", description="TTS provider used if primary fails to load"
    )
    tts_voice: str = Field(
        default="tara",
        description="Voice identifier (Orpheus: tara/leah/jess/leo/dan/mia/zac/zoe; Kokoro: af_nicole etc.)",
    )
    orpheus_model_path: str = Field(
        default="models/orpheus-3b-0.1-ft-q4_k_m.gguf",
        description="Path to the Orpheus GGUF (relative to Emily root)",
    )
    orpheus_main_gpu: int = Field(
        default=1, description="CUDA device index for Orpheus GGUF (1 = 3060)"
    )
    orpheus_snac_device: str = Field(
        default="cuda:1",
        description="Torch device for SNAC decoding ('cuda:1' or 'cpu')",
    )

    # ── Audio I/O ─────────────────────────────────
    audio_input_device: str = Field(
        default="", description="Input device name or index (empty = system default)"
    )
    audio_output_device: str = Field(
        default="", description="Output device name or index (empty = system default)"
    )

    # ── VAD ────────────────────────────────────────
    vad_threshold: float = Field(default=0.5, description="VAD confidence threshold")
    min_speech_ms: int = Field(default=200, description="Minimum speech duration in ms")
    min_silence_ms: int = Field(default=800, description="Minimum silence duration in ms")

    # ── System Prompt ─────────────────────────────
    system_prompt: str = Field(default="", description="Optional custom system prompt")

    def get_system_prompt(self) -> str:
        """Return the configured system prompt, falling back to prompt_builder."""
        if self.system_prompt.strip():
            return self.system_prompt.strip()
        return _get_default_system_prompt()
