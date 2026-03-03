"""Voice Engine configuration via environment variables and .env file."""

from __future__ import annotations

import logging

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "You are a friendly, concise voice assistant. "
    "Respond naturally as if in a real-time spoken conversation. "
    "Keep answers short and to the point — ideally one to three sentences — "
    "unless the user explicitly asks for more detail. "
    "Never use emojis, emoticons, or Unicode symbols in your responses. "
    "Never use markdown formatting, bullet points, asterisks, or numbered lists. "
    "Write only plain spoken sentences because your output will be read aloud. "
    "If you don't know something, say so briefly rather than speculating."
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
    elevenlabs_api_key: str = Field(default="", description="ElevenLabs API key")
    tabby_api_key: str = Field(default="", description="TabbyAPI admin key (optional)")

    # ── STT ────────────────────────────────────────
    stt_provider: str = Field(default="faster_whisper", description="STT provider name")
    stt_model: str = Field(default="distil-large-v3", description="STT model identifier")

    # ── LLM ────────────────────────────────────────
    llm_provider: str = Field(default="ollama", description="LLM provider name")
    llm_model: str = Field(default="llama3.2", description="LLM model identifier")
    llm_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for OpenAI-compatible APIs",
    )

    # ── TTS ────────────────────────────────────────
    tts_provider: str = Field(default="kokoro", description="TTS provider name")
    tts_voice: str = Field(default="af_heart", description="TTS voice identifier")
    chatterbox_exaggeration: float = Field(
        default=0.5, description="Chatterbox emotion exaggeration (0.0–1.0)"
    )
    chatterbox_ref_audio: str = Field(
        default="", description="Reference audio path for Chatterbox voice cloning"
    )
    emotion_threshold: float = Field(
        default=0.6,
        description="Emotional dimension threshold for tiered TTS routing to expressive",
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
        """Return the configured system prompt, falling back to a sensible default."""
        if self.system_prompt.strip():
            return self.system_prompt.strip()
        return _DEFAULT_SYSTEM_PROMPT
