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
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class LLMModels(BaseModel):
    nano: str = "qwen3:4b"
    voice_fast: str = "qwen3:4b"
    fast: str = "qwen3:14b"
    smart: str = "qwq:latest"
    reasoning: str = "qwq:latest"
    vision: str = "minicpm-v:latest"
    embedding: str = "bge-m3"


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
    fast: str = "ollama"
    smart: str = "ollama"
    reasoning: str = "ollama"
    vision: str = "ollama"
    embedding: str = "ollama"

    @field_validator("*")
    @classmethod
    def validate_backend(cls, v: str) -> str:
        """Ensure backend value is a recognised option."""
        allowed = {"ollama", "llamacpp"}
        if v not in allowed:
            raise ValueError(f"tier_backend must be one of {allowed}, got {v!r}")
        return v


class LLMConfig(BaseModel):
    backend: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    models: LLMModels = Field(default_factory=LLMModels)
    routing: LLMRouting = Field(default_factory=LLMRouting)
    inference: LLMInference = Field(default_factory=LLMInference)
    critic: LLMCritic = Field(default_factory=LLMCritic)
    llamacpp: LlamaCppConfig = Field(default_factory=LlamaCppConfig)
    tier_backend: TierBackend = Field(default_factory=TierBackend)


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    input_device: str | None = None
    output_device: str | None = None


class VoiceEngineConfig(BaseModel):
    enabled: bool = True
    input_sample_rate: int = 48000
    output_sample_rate: int = 24000
    output_channels: int = 2
    chunk_ms: int = 10
    aec_enabled: bool = True
    aec_tail_ms: int = 150
    noise_suppress_enabled: bool = True
    noise_threshold_db: float = 15.0
    speaker_tracking: bool = True
    max_speakers: int = 2
    turn_response_threshold: float = 0.85
    turn_backchannel_threshold: float = 0.45
    backchannels_enabled: bool = True
    fillers_enabled: bool = True
    breathing_enabled: bool = True
    rhythm_sync_enabled: bool = True
    entrainment_degree: float = 0.4
    emotion_adapt_enabled: bool = True
    whisper_match: bool = True
    energy_match: bool = True
    cross_session_rhythm: bool = True
    latency_target_ms: int = 500
    speculative_generation: bool = True
    speculative_start_probability: float = 0.65
    fast_mode: bool = True
    fast_mode_skip_speaker_tracking: bool = True
    fast_mode_skip_emotion: bool = True
    fast_mode_skip_breathing: bool = True
    fast_mode_skip_rhythm: bool = True
    interrupt_energy_threshold: float = 0.03
    interrupt_cooldown_ms: int = 300
    interrupt_fade_ms: int = 20
    interrupt_lookahead_ms: int = 300
    interrupt_ack_enabled: bool = True
    interrupt_resume_enabled: bool = True
    interrupt_resume_expiry_s: float = 30.0
    interrupt_adaptive_threshold: bool = True


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
    model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str | None = None
    word_timestamps: bool = True
    beam_size: int = 5
    voice_fast_beam_size: int = 1


class XTTSConfig(BaseModel):
    model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    speaker_wav: str | None = None
    language: str = "en"
    speed: float = 1.0


class KokoroConfig(BaseModel):
    voice: str = "af_sky"
    speed: float = 1.0


class CSMConfig(BaseModel):
    """Sesame CSM (Conversational Speech Model) configuration."""

    model_id: str = "sesame/csm-1b"
    speaker_id: int = 0
    max_audio_length: int = 250
    dtype: str = "float16"


class TTSConfig(BaseModel):
    primary: str = "xtts_v2"
    fallback: str = "kokoro"
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
    web_search_url: str = "http://localhost:8080"
    home_assistant: HomeAssistantConfig = Field(default_factory=HomeAssistantConfig)


class VisionConfig(BaseModel):
    enabled: bool = True
    screen_capture_interval_s: float = 5.0
    webcam_capture_interval_s: float = 5.0
    webcam_device: int = 0
    emotion_detection: bool = True
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
    dead_man_switch_days: int = 30
    require_approval_tools: list[str] = Field(
        default_factory=lambda: ["shell", "process_manager", "file_writer"]
    )


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
    metrics_port: int = 9090
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
    def from_yaml(cls, path: str | Path = "config.yaml") -> "EmilySettings":
        """Load settings from a YAML file, then apply env var overrides."""
        yaml_path = Path(path)
        init_kwargs: dict[str, Any] = {}

        if yaml_path.exists():
            with yaml_path.open("r") as fh:
                raw = yaml.safe_load(fh) or {}
            # Top-level key is optional 'emily:' wrapper
            init_kwargs = raw.get("emily", raw) if "emily" in raw else raw
            # Merge all top-level sections
            for key in [
                "llm", "audio", "wake_word", "vad", "stt", "tts",
                "singing", "voice_engine", "memory", "knowledge", "vault",
                "rag", "agents", "tools", "vision", "persona", "security",
                "self_improvement", "api", "observability",
            ]:
                if key in raw:
                    init_kwargs[key] = raw[key]

        return cls(**init_kwargs)


@lru_cache(maxsize=1)
def get_settings() -> EmilySettings:
    """Return the singleton settings instance (cached after first load)."""
    config_path = os.environ.get("EMILY_CONFIG", "config.yaml")
    return EmilySettings.from_yaml(config_path)
