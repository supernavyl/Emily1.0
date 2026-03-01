"""
Emily configuration system.

All runtime configuration is loaded from config.yaml, with environment variable
overrides following the pattern EMILY__<SECTION>__<KEY>=value.
Pydantic Settings v2 is used for validation and type safety.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class LLMModels(BaseModel):
    nano: str = "qwen3-4b-abliterated"
    voice_fast: str = "qwen3-4b-abliterated"
    fast: str = "Qwen2.5-14B-Instruct-abliterated"
    smart: str = "qwq-32b-abliterated"
    reasoning: str = "qwq-32b-abliterated"
    vision: str = "minicpm-v:latest"
    embedding: str = "bge-m3"
    cloud_best: str = "claude-opus-4-6"
    cloud_fast: str = "claude-sonnet-4-6"


class LLMRouting(BaseModel):
    complexity_threshold_fast: int = 3
    complexity_threshold_smart: int = 7
    voice_fast_complexity_threshold: int = 5
    voice_skip_rag_below: int = 5
    voice_skip_critic: bool = True
    vram_headroom_gb: float = 2.0
    default_stream: bool = True


class LLMInference(BaseModel):
    temperature: float = 0.7
    top_p: float = 0.9
    repeat_penalty: float = 1.1
    max_tokens: int = 4096
    context_window: int = 8192


class TierInferenceOverride(BaseModel):
    """Per-tier inference parameter overrides applied on top of LLMInference defaults."""

    temperature: float | None = None
    max_tokens: int | None = None
    enable_thinking: bool = (
        True  # Controls Qwen3/QwQ <think> blocks and Anthropic extended thinking
    )
    thinking_budget: int | None = None  # Token budget for extended thinking (Anthropic only)


class TierInferenceConfig(BaseModel):
    """Per-tier inference overrides for each model tier."""

    nano: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=0.3, max_tokens=512, enable_thinking=False
        )
    )
    voice_fast: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=0.7, max_tokens=1024, enable_thinking=False
        )
    )
    fast: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=0.7, max_tokens=4096, enable_thinking=True
        )
    )
    smart: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=0.6, max_tokens=8192, enable_thinking=True
        )
    )
    reasoning: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=0.6, max_tokens=16384, enable_thinking=True
        )
    )
    cloud_best: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=1.0, max_tokens=16384, enable_thinking=True, thinking_budget=16_000
        )
    )
    cloud_fast: TierInferenceOverride = Field(
        default_factory=lambda: TierInferenceOverride(
            temperature=1.0, max_tokens=8192, enable_thinking=True, thinking_budget=8_000
        )
    )

    def for_tier(self, tier_name: str) -> TierInferenceOverride:
        """Get overrides for a given tier name, defaulting to smart settings."""
        return getattr(self, tier_name, self.smart)


class LLMCritic(BaseModel):
    enabled: bool = True
    min_confidence: float = 0.65
    max_retries: int = 2


class LlamaCppModelConfig(BaseModel):
    """Per-model settings for a GGUF loaded via llama-cpp-python."""

    filename: str = ""
    alias_of: str | None = None
    n_gpu_layers: int = -1
    n_ctx: int = 8192
    n_batch: int = 512


class LlamaCppConfig(BaseModel):
    """Top-level llama-cpp-python backend configuration."""

    enabled: bool = False
    models_dir: str = "models"
    models: dict[str, LlamaCppModelConfig] = Field(default_factory=dict)


class TierBackend(BaseModel):
    """Which inference backend to use for each model tier."""

    nano: str = "llamacpp"
    voice_fast: str = "llamacpp"
    fast: str = "tabbyapi"
    smart: str = "tabbyapi"
    reasoning: str = "tabbyapi"
    vision: str = "ollama"
    embedding: str = "ollama"
    cloud_best: str = "anthropic"
    cloud_fast: str = "anthropic"

    @field_validator("*")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Ensure backend value is a recognised option."""
        allowed = {"ollama", "llamacpp", "tabbyapi", "anthropic"}
        if v not in allowed:
            raise ValueError(f"tier_backend must be one of {allowed}, got {v!r}")
        return v


class LLMConfig(BaseModel):
    backend: str = "tabbyapi"
    ollama_base_url: str = "http://localhost:11434"
    tabbyapi_base_url: str = "http://localhost:5000"
    tabbyapi_api_key: str = ""
    models: LLMModels = Field(default_factory=LLMModels)
    routing: LLMRouting = Field(default_factory=LLMRouting)
    inference: LLMInference = Field(default_factory=LLMInference)
    tier_inference: TierInferenceConfig = Field(default_factory=TierInferenceConfig)
    critic: LLMCritic = Field(default_factory=LLMCritic)
    llamacpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    tier_backend: TierBackend = Field(default_factory=TierBackend)


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    input_device: str | int | None = None
    output_device: str | int | None = None


class VoiceEngineConfig(BaseModel):
    """VoiceEngine 1.3 — provider-agnostic voice conversation engine.

    Most settings are read from .env by the engine's own VoiceEngineConfig
    (pydantic-settings). This wrapper just controls whether Bootstrap starts it.
    """

    enabled: bool = True
    stt_provider: str = "faster_whisper"
    llm_provider: str = "ollama"
    tts_provider: str = "kokoro"
    vad_threshold: float = 0.5
    min_speech_ms: int = 200
    min_silence_ms: int = 800


class WakeWordConfig(BaseModel):
    model: str = "hey_emily"
    threshold: float = 0.5
    inference_framework: str = "onnx"
    custom_model_path: str | None = None


class VADConfig(BaseModel):
    model: str = "silero"
    threshold: float = 0.5
    min_silence_ms: int = 500
    min_speech_ms: int = 250
    adaptive: bool = True
    noise_floor_update_rate: float = 0.01


class STTConfig(BaseModel):
    profile: Literal["fast", "accurate"] = "fast"
    model: str = "large-v3-turbo"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str | None = "en"
    word_timestamps: bool = True
    beam_size: int = 5
    voice_fast_beam_size: int = 1
    voice_accurate_beam_size: int = 3
    streaming_window_duration_s: float = 3.0
    streaming_process_interval_s: float = 0.15
    streaming_min_buffer_s: float = 0.3
    streaming_commit_skip_threshold_s: float = 0.2
    streaming_rms_gate_threshold: float = 0.006
    streaming_commit_confidence: float = 0.7
    streaming_reject_low_confidence: float = 0.65
    streaming_min_final_words: int = 3
    streaming_min_unique_ratio: float = 0.45
    streaming_max_repeat_ratio: float = 0.6
    streaming_short_utterance_confidence: float = 0.8
    use_whisper_vad: bool = False
    whisper_vad_threshold: float = 0.1
    whisper_vad_min_speech_ms: int = 0
    whisper_vad_min_silence_ms: int = 300
    no_speech_threshold: float = 0.7


class XTTSConfig(BaseModel):
    model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    speaker_wav: str | None = None
    language: str = "en"
    speed: float = 1.0


class KokoroConfig(BaseModel):
    voice: str = "af_heart"
    speed: float = 1.0


class CSMConfig(BaseModel):
    """Sesame CSM (Conversational Speech Model) configuration."""

    model_id: str = "sesame/csm-1b"
    speaker_id: int = 0
    max_audio_length: int = 250
    dtype: str = "float16"


class TTSConfig(BaseModel):
    primary: str = "kokoro"
    fallback: str = "xtts_v2"
    voice_preset: str = "en_US_female_1"
    xtts: XTTSConfig = Field(default_factory=XTTSConfig)
    kokoro: KokoroConfig = Field(default_factory=KokoroConfig)
    csm: CSMConfig = Field(default_factory=CSMConfig)
    streaming_chunk_size: int = 100


class WorkingMemoryConfig(BaseModel):
    max_tokens: int = 4096
    pin_important_threshold: float = 0.8


class EpisodicMemoryConfig(BaseModel):
    db_path: str = "data/episodes.db"
    auto_summarize: bool = True
    summary_model: str = "fast"
    save_all_interactions: bool = True  # Save every user/assistant turn immediately
    interactions_db_path: str = "data/interactions.db"  # Separate DB for all turns
    auto_backup_interval_minutes: int = 30  # Auto-backup every 30 minutes


class SemanticMemoryConfig(BaseModel):
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "emily_semantic"
    bm25_index_path: str = "data/bm25_index"
    temporal_decay_days: int = 365
    decay_factor: float = 0.95


class ProceduralMemoryConfig(BaseModel):
    path: str = "data/procedural.json"


class ConsolidationConfig(BaseModel):
    idle_trigger_minutes: int = 10
    max_episodes_per_run: int = 20
    reflection_model: str = "smart"


class MemoryConfig(BaseModel):
    sensory_buffer_size: int = 1000
    working: WorkingMemoryConfig = Field(default_factory=WorkingMemoryConfig)
    episodic: EpisodicMemoryConfig = Field(default_factory=EpisodicMemoryConfig)
    semantic: SemanticMemoryConfig = Field(default_factory=SemanticMemoryConfig)
    procedural: ProceduralMemoryConfig = Field(default_factory=ProceduralMemoryConfig)
    consolidation: ConsolidationConfig = Field(default_factory=ConsolidationConfig)


class RAGConfig(BaseModel):
    watch_dirs: list[str] = Field(default_factory=lambda: ["knowledge"])
    chunk_size_child: int = 256
    chunk_size_parent: int = 2048
    chunk_overlap: int = 32
    embedding_batch_size: int = 32
    query_expansion_count: int = 3
    rerank_top_k: int = 20
    final_top_k: int = 5


class AgentsConfig(BaseModel):
    message_bus_port: int = 5555
    heartbeat_interval_s: int = 5
    task_timeout_s: int = 60
    reflection_interval_minutes: int = 10
    monitor_interval_s: int = 30


class HomeAssistantConfig(BaseModel):
    url: str = "http://localhost:8123"
    token: str | None = None


class ToolsConfig(BaseModel):
    sandbox: str = "bubblewrap"
    allowed_paths: list[str] = Field(default_factory=list)
    web_search_url: str = "http://localhost:8888"
    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)


class VisionConfig(BaseModel):
    enabled: bool = False
    screen_capture_interval_s: float = 5.0
    webcam_capture_interval_s: float = 5.0
    webcam_device: int = 0
    emotion_detection: bool = False
    presence_idle_threshold_s: float = 120.0


class RVCConfig(BaseModel):
    """RVC singing voice conversion settings."""

    enabled: bool = True
    model_path: str | None = None
    index_path: str | None = None
    device: str = "cuda:0"
    f0_method: str = "rmvpe"
    transpose: int = 0

    @field_validator("f0_method")
    @classmethod
    def validate_f0_method(cls, v: str) -> str:
        allowed = {"rmvpe", "crepe", "harvest", "pm", "dio"}
        if v not in allowed:
            raise ValueError(f"f0_method must be one of {allowed}, got {v!r}")
        return v


class MusicGenConfig(BaseModel):
    """AudioCraft MusicGen settings."""

    enabled: bool = True
    model_size: str = "small"
    duration_seconds: int = 30
    device: str = "cuda:0"

    @field_validator("model_size")
    @classmethod
    def validate_model_size(cls, v: str) -> str:
        allowed = {"small", "medium", "large"}
        if v not in allowed:
            raise ValueError(f"model_size must be one of {allowed}, got {v!r}")
        return v


class SunoConfig(BaseModel):
    """Suno cloud API settings."""

    enabled: bool = True
    api_url: str = "https://api.sunoapi.org"
    api_key: str | None = None
    model_version: str = "v4"
    timeout_seconds: int = 120


class SingingConfig(BaseModel):
    """Top-level singing / music generation configuration."""

    enabled: bool = True
    primary: str = "musicgen"
    fallback: str = "suno"
    output_dir: str = "data/singing_output"
    rvc: RVCConfig = Field(default_factory=RVCConfig)
    musicgen: MusicGenConfig = Field(default_factory=MusicGenConfig)
    suno: SunoConfig = Field(default_factory=SunoConfig)

    @field_validator("primary", "fallback")
    @classmethod
    def validate_engine_name(cls, v: str) -> str:
        allowed = {"musicgen", "rvc", "suno"}
        if v not in allowed:
            raise ValueError(f"singing engine must be one of {allowed}, got {v!r}")
        return v


class PersonaConfig(BaseModel):
    profile_path: str = "persona/profile.json"
    curiosity: float = 0.8
    warmth: float = 0.85
    directness: float = 0.7
    humor: float = 0.5
    formality: float = 0.3
    evolution_rate: float = 0.01


class KnowledgeStoreConfig(BaseModel):
    db_path: str = "data/knowledge.db"
    min_fact_confidence: float = 0.4


class VaultConfig(BaseModel):
    db_path: str = "data/vault.db"
    auto_lock_minutes: int = 5
    clipboard_clear_seconds: int = 30
    audit_log_path: str = "logs/vault_audit.log"
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536
    argon2_parallelism: int = 4


class SecurityConfig(BaseModel):
    encrypt_at_rest: bool = True
    key_file: str = "~/.emily_key"
    pii_scrub: bool = True
    audit_log_path: str = "logs/audit.log"
    audit_retention_days: int = 90
    dead_man_switch_days: int = 30
    dead_man_switch_heartbeat_path: str = "data/.emily_last_active"
    require_approval_tools: list[str] = Field(
        default_factory=lambda: ["shell", "process_manager", "file_writer"]
    )


class OwnerConfig(BaseModel):
    """Single owner identity and privacy configuration."""

    enabled: bool = True
    identity_file: str = "data/owner_identity.json"
    require_verification: bool = True
    verification_timeout_minutes: int = 60
    guest_mode_enabled: bool = True
    share_personal_with_guests: bool = False  # NEVER share personal info
    lockout_after_failed_attempts: int = 3
    lockout_duration_minutes: int = 5


class SelfImprovementConfig(BaseModel):
    track_performance: bool = True
    evolve_prompts: bool = True
    prompt_ab_test_sessions: int = 10
    capability_gap_log: str = "data/capability_gaps.jsonl"
    performance_log: str = "data/performance_log.jsonl"


class APIConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False
    secret_key: str | None = None
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:8000",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ]
    )
    rate_limit_requests: int = 100
    rate_limit_window_s: int = 60
    max_body_size_bytes: int = 1_000_000  # 1 MB; reject larger request bodies


class ObservabilityConfig(BaseModel):
    otlp_endpoint: str = "http://localhost:4317"
    metrics_port: int = 9091
    log_format: str = "json"
    tracing_enabled: bool = True


# ---------------------------------------------------------------------------
# Root settings
# ---------------------------------------------------------------------------


class EmilySettings(BaseSettings):
    """Root settings object. Loaded from config.yaml + env overrides."""

    model_config = SettingsConfigDict(
        env_prefix="EMILY_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    name: str = "Emily"
    version: str = "1.0.0"
    log_level: str = "INFO"
    data_dir: str = "data"
    logs_dir: str = "logs"
    knowledge_dir: str = "knowledge"
    prompts_dir: str = "prompts"

    llm: LLMConfig = Field(default_factory=LLMConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    wake_word: WakeWordConfig = Field(default_factory=WakeWordConfig)
    vad: VADConfig = Field(default_factory=VADConfig)
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    singing: SingingConfig = Field(default_factory=SingingConfig)
    voice_engine: VoiceEngineConfig = Field(default_factory=VoiceEngineConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    knowledge: KnowledgeStoreConfig = Field(default_factory=KnowledgeStoreConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    owner: OwnerConfig = Field(default_factory=OwnerConfig)
    self_improvement: SelfImprovementConfig = Field(default_factory=SelfImprovementConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is a valid Python logging level."""
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got {v!r}")
        return upper

    @classmethod
    def from_yaml(cls, path: str | Path = "config.yaml") -> EmilySettings:
        """Load settings from a YAML file, then apply env var overrides."""
        yaml_path = Path(path)
        init_kwargs: dict[str, Any] = {}

        if yaml_path.exists():
            with yaml_path.open("r") as fh:
                raw = cast("dict[str, Any]", yaml.safe_load(fh) or {})
            init_kwargs = raw.get("emily", raw) if "emily" in raw else raw
            # Merge all top-level sections
            for key in [
                "llm",
                "audio",
                "wake_word",
                "vad",
                "stt",
                "tts",
                "singing",
                "voice_engine",
                "memory",
                "knowledge",
                "vault",
                "rag",
                "agents",
                "tools",
                "vision",
                "persona",
                "security",
                "owner",
                "self_improvement",
                "api",
                "observability",
            ]:
                if key in raw:
                    init_kwargs[key] = raw[key]

        return cls(**init_kwargs)


@lru_cache(maxsize=1)
def get_settings() -> EmilySettings:
    """Return the singleton settings instance (cached after first load)."""
    config_path = os.environ.get("EMILY_CONFIG", "config.yaml")
    return EmilySettings.from_yaml(config_path)
