"""Factory for creating provider instances based on configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

from observability.logger import get_logger

if TYPE_CHECKING:
    from voice_engine.config import VoiceEngineConfig
    from voice_engine.providers.base import LLMProvider, STTProvider, TTSProvider

logger = get_logger(__name__)


class ProviderFactory:
    """Lazily instantiate STT / LLM / TTS providers by config name."""

    @staticmethod
    def create_stt(config: VoiceEngineConfig) -> STTProvider:
        """Create and return an STT provider based on ``config.stt_provider``."""
        name = config.stt_provider.lower().strip()
        logger.info("Creating STT provider: %s (model=%s)", name, config.stt_model)

        if name == "faster_whisper":
            from voice_engine.providers.stt.faster_whisper import FasterWhisperSTT

            return FasterWhisperSTT(
                model_size=config.stt_model,
                device=config.stt_device,
                device_index=config.stt_device_index,
                compute_type=config.stt_compute_type,
            )

        if name == "openai":
            from voice_engine.providers.stt.openai_stt import OpenAISTT

            return OpenAISTT(api_key=config.openai_api_key, model=config.stt_model)

        if name == "deepgram":
            from voice_engine.providers.stt.deepgram_stt import DeepgramSTT

            return DeepgramSTT(api_key=config.deepgram_api_key)

        raise ValueError(f"Unknown STT provider: {name!r}")

    @staticmethod
    def create_llm(config: VoiceEngineConfig) -> LLMProvider:
        """Create and return an LLM provider based on ``config.llm_provider``."""
        name = config.llm_provider.lower().strip()
        logger.info("Creating LLM provider: %s (model=%s)", name, config.llm_model)

        if name == "ollama":
            from voice_engine.providers.llm.ollama_llm import OllamaLLM

            return OllamaLLM(model=config.llm_model, base_url=config.llm_base_url)

        if name == "openai":
            from voice_engine.providers.llm.openai_llm import OpenAILLM

            return OpenAILLM(
                api_key=config.openai_api_key,
                model=config.llm_model,
                base_url=config.llm_base_url if config.llm_base_url else None,
            )

        if name == "claude":
            from voice_engine.providers.llm.claude_llm import ClaudeLLM

            return ClaudeLLM(api_key=config.anthropic_api_key, model=config.llm_model)

        if name == "groq":
            from voice_engine.providers.llm.groq_llm import GroqLLM

            return GroqLLM(api_key=config.groq_api_key, model=config.llm_model)

        if name == "tabby":
            from voice_engine.providers.llm.tabby_llm import TabbyLLM

            return TabbyLLM(
                model=config.llm_model,
                base_url=config.llm_base_url or "http://localhost:5000/v1",
                api_key=config.tabby_api_key,
            )

        if name == "llamacpp":
            from voice_engine.providers.llm.llamacpp_llm import LlamaCppLLM

            return LlamaCppLLM(
                model=config.llm_model,
                base_url=config.llm_base_url or "http://localhost:8080/v1",
            )

        raise ValueError(f"Unknown LLM provider: {name!r}")

    @staticmethod
    def create_tts(config: VoiceEngineConfig) -> TTSProvider:
        """Create and return a TTS provider based on ``config.tts_provider``."""
        name = config.tts_provider.lower().strip()
        logger.info("Creating TTS provider: %s (voice=%s)", name, config.tts_voice)

        if name == "orpheus":
            from voice_engine.providers.tts.orpheus_tts import OrpheusTTS

            try:
                return OrpheusTTS(
                    model_path=config.orpheus_model_path,
                    voice=config.tts_voice,
                    main_gpu=config.orpheus_main_gpu,
                    snac_device=config.orpheus_snac_device,
                )
            except Exception:
                logger.exception(
                    "OrpheusTTS failed to initialize; falling back to %s",
                    config.tts_fallback,
                )
                if config.tts_fallback == "kokoro":
                    from voice_engine.providers.tts.kokoro_tts import KokoroTTS

                    return KokoroTTS(voice="af_nicole")
                raise

        if name in ("kokoro", "tiered"):
            from voice_engine.providers.tts.kokoro_tts import KokoroTTS

            voice = config.tts_voice if config.tts_voice.startswith("af_") else "af_nicole"
            return KokoroTTS(voice=voice)

        raise ValueError(f"Unknown TTS provider: {name!r}. Supported: 'orpheus', 'kokoro'.")
