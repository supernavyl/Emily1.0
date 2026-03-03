"""ModelSpec definition and the global EMILY_MODEL_REGISTRY.

Every model Emily can talk through is declared here.  The registry is the
single source of truth for pricing, capabilities, context-window limits,
and display metadata.

Phase 6 added OpenAI entries.  Phase 7 adds Google Gemini 3 / 2.5.
Phase 8 adds Groq, xAI, DeepSeek, Together, and Mistral entries.
Phase 9 adds OpenRouter (Kimi K2, GLM 4.7, custom) and Ollama (local).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """Immutable descriptor for a single LLM endpoint.

    Attributes are loosely typed where the spec may evolve (e.g. *tier*,
    *speed*).  Pricing is per-million tokens.
    """

    display: str
    provider: str
    model_id: str
    context: int = 128_000
    thinking: bool = False
    vision: bool = False
    audio: bool = False
    video: bool = False
    input_usd: float = 0.0
    output_usd: float = 0.0
    speed: str = "fast"
    tier: str = "good"
    default: bool = False
    open_weights: bool = False
    license: str = ""
    best_for: tuple[str, ...] = ()
    notes: str = ""
    reasoning_effort: tuple[str, ...] = ()

    @property
    def is_reasoning_model(self) -> bool:
        """True for o-series models that use reasoning_effort instead of temperature."""
        return bool(self.reasoning_effort)


# ---------------------------------------------------------------------------
# Anthropic entries
# ---------------------------------------------------------------------------

EMILY_MODEL_REGISTRY: dict[str, ModelSpec] = {
    # -----------------------------------------------------------------------
    # Local models (emily-* entries) are registered dynamically at startup
    # by LLMFleet._register_config_models() from config.yaml tier mappings.
    # Only static cloud provider entries are defined here.
    # -----------------------------------------------------------------------
    # Anthropic entries
    # -----------------------------------------------------------------------
    "claude-sonnet-4-6": ModelSpec(
        display="Emily \u2014 Claude Sonnet 4.6",
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        context=200_000,
        thinking=True,
        vision=True,
        input_usd=3.00,
        output_usd=15.00,
        speed="fast",
        tier="excellent",
        best_for=("coding", "analysis", "creative writing", "general tasks"),
        notes="Best balance of speed, quality, and cost.",
    ),
    "claude-opus-4-6": ModelSpec(
        display="Emily \u2014 Claude Opus 4.6",
        provider="anthropic",
        model_id="claude-opus-4-6",
        context=200_000,
        thinking=True,
        vision=True,
        input_usd=15.00,
        output_usd=75.00,
        speed="slow",
        tier="best",
        best_for=(
            "complex reasoning",
            "research",
            "long-form analysis",
            "reflection",
            "self-model updates",
            "planning",
            "agentic tasks",
            "deep synthesis",
            "multi-step strategy",
        ),
        notes=(
            "Emily's cloud brain. Routes here automatically for reflection, "
            "planning, and complex agent tasks (CLOUD_BEST tier). "
            "Extended thinking budget: 16 000 tokens. Requires ANTHROPIC_API_KEY."
        ),
    ),
    "claude-haiku-4-5": ModelSpec(
        display="Emily \u2014 Claude Haiku 4.5",
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
        context=200_000,
        vision=True,
        input_usd=0.80,
        output_usd=4.00,
        speed="very-fast",
        tier="good",
        best_for=("quick tasks", "classification", "extraction"),
        notes="Fastest and most affordable Anthropic model.",
    ),
    # -----------------------------------------------------------------------
    # OpenAI entries (Phase 6)
    # -----------------------------------------------------------------------
    "gpt-5-2": ModelSpec(
        display="Emily \u2014 GPT-5.2",
        provider="openai",
        model_id="gpt-5.2",
        context=256_000,
        vision=True,
        audio=True,
        input_usd=15.00,
        output_usd=60.00,
        speed="medium",
        tier="best",
        best_for=("professional tasks", "knowledge work", "enterprise", "creative"),
        notes="First model to exceed human experts on 70.9% of pro tasks.",
    ),
    "gpt-5": ModelSpec(
        display="Emily \u2014 GPT-5",
        provider="openai",
        model_id="gpt-5",
        context=256_000,
        vision=True,
        input_usd=8.00,
        output_usd=32.00,
        speed="fast",
        tier="excellent",
        best_for=("general tasks", "vision", "coding", "writing"),
    ),
    "gpt-4o": ModelSpec(
        display="Emily \u2014 GPT-4o",
        provider="openai",
        model_id="gpt-4o",
        context=128_000,
        vision=True,
        input_usd=2.50,
        output_usd=10.00,
        speed="fast",
        tier="very-good",
        best_for=("cost-conscious quality", "general tasks"),
        notes="Excellent value even with GPT-5 available.",
    ),
    "o3": ModelSpec(
        display="Emily \u2014 o3 Reasoning",
        provider="openai",
        model_id="o3",
        context=200_000,
        thinking=True,
        input_usd=10.00,
        output_usd=40.00,
        speed="slow",
        tier="best-reasoning",
        best_for=("math", "logic", "proofs", "competitive coding", "science"),
        notes="Best pure reasoning. Use for problems that can't be shortcut.",
        reasoning_effort=("low", "medium", "high"),
    ),
    "o4-mini": ModelSpec(
        display="Emily \u2014 o4-mini",
        provider="openai",
        model_id="o4-mini",
        context=200_000,
        thinking=True,
        input_usd=1.10,
        output_usd=4.40,
        speed="medium",
        tier="excellent",
        best_for=("fast reasoning", "math", "code debugging"),
        notes="Best reasoning-per-dollar in 2026.",
        reasoning_effort=("low", "medium", "high"),
    ),
    # ── Google Gemini 3 / 2.5 series (Phase 7) ─────────────────────────
    "gemini-3-pro": ModelSpec(
        display="Emily \u2014 Gemini 3 Pro",
        provider="google",
        model_id="gemini-3-pro-preview",
        context=2_000_000,
        thinking=True,
        vision=True,
        video=True,
        audio=True,
        input_usd=2.50,
        output_usd=15.00,
        speed="medium",
        tier="best-multimodal",
        best_for=("massive docs", "multimodal", "video", "science", "2M context"),
        notes="Dethroned GPT-5 on 19/20 benchmarks. #1 HLE score.",
    ),
    "gemini-3-flash": ModelSpec(
        display="Emily \u2014 Gemini 3 Flash",
        provider="google",
        model_id="gemini-3-flash",
        context=1_000_000,
        thinking=True,
        vision=True,
        input_usd=0.10,
        output_usd=0.40,
        speed="ultra-fast",
        tier="excellent",
        best_for=("fast deep reasoning", "1M ctx cheap", "PhD-level on budget"),
        notes="PhD-level reasoning at fraction of Pro cost.",
    ),
    "gemini-2-5-pro": ModelSpec(
        display="Emily \u2014 Gemini 2.5 Pro",
        provider="google",
        model_id="gemini-2.5-pro-preview",
        context=1_000_000,
        thinking=True,
        vision=True,
        input_usd=1.25,
        output_usd=10.00,
        speed="medium",
        tier="very-good",
        best_for=("large context", "cost-conscious deep analysis"),
    ),
    # ── Groq — ultra-low-latency LPU inference (Phase 8) ─────────────
    "groq-llama-70b": ModelSpec(
        display="Emily \u2014 Instant",
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        context=128_000,
        input_usd=0.59,
        output_usd=0.79,
        speed="blazing",
        tier="very-good",
        open_weights=True,
        best_for=("real-time chat", "~80ms first token", "quick answers"),
        notes="Fastest first-token. Best for latency-critical scenarios.",
    ),
    "groq-deepseek-r1": ModelSpec(
        display="Emily \u2014 Fast Think",
        provider="groq",
        model_id="deepseek-r1-distill-llama-70b",
        context=128_000,
        thinking=True,
        input_usd=0.75,
        output_usd=0.99,
        speed="blazing",
        tier="excellent",
        open_weights=True,
        best_for=("fast reasoning", "math", "debugging", "think at Groq speed"),
    ),
    "qwen3-72b": ModelSpec(
        display="Emily \u2014 Qwen3 72B Fast",
        provider="groq",
        model_id="qwen3-72b",
        context=128_000,
        thinking=True,
        input_usd=0.29,
        output_usd=0.39,
        speed="blazing",
        tier="very-good",
        open_weights=True,
        license="Apache-2.0",
        best_for=("fast multilingual", "budget reasoning on Groq"),
    ),
    "llama-4-scout": ModelSpec(
        display="Emily \u2014 Llama Scout",
        provider="groq",
        model_id="meta-llama/llama-4-scout-17b-16e-instruct",
        context=10_000_000,
        input_usd=0.11,
        output_usd=0.34,
        speed="fast",
        tier="good",
        open_weights=True,
        best_for=("entire codebase in context", "10M token analysis", "legal review"),
        notes="Industry-leading 10M token window. Feed entire repos.",
    ),
    # ── xAI Grok 4.1 (Phase 8) ──────────────────────────────────────
    "grok-4-1": ModelSpec(
        display="Emily \u2014 Grok 4.1",
        provider="xai",
        model_id="grok-4.1",
        context=256_000,
        vision=True,
        input_usd=5.00,
        output_usd=15.00,
        speed="fast",
        tier="excellent",
        best_for=("creative writing", "humor", "sarcasm", "cultural nuance", "storytelling"),
        notes="#1 EQ benchmark. Most human-sounding commercial model.",
    ),
    # ── DeepSeek V3.2 + R2 (Phase 8) ────────────────────────────────
    "deepseek-v3-2": ModelSpec(
        display="Emily \u2014 DeepSeek V3",
        provider="deepseek",
        model_id="deepseek-v3.2-special",
        context=128_000,
        input_usd=0.27,
        output_usd=1.10,
        speed="fast",
        tier="excellent",
        open_weights=True,
        license="MIT",
        best_for=("coding", "math", "90%-quality at 1/10th cost"),
        notes="Matches frontier on coding/reasoning at ~1/10th cost.",
    ),
    "deepseek-r2": ModelSpec(
        display="Emily \u2014 DeepSeek R2",
        provider="deepseek",
        model_id="deepseek-r2",
        context=128_000,
        thinking=True,
        input_usd=0.55,
        output_usd=2.19,
        speed="medium",
        tier="excellent",
        open_weights=True,
        license="MIT",
        best_for=("reasoning", "math", "science", "budget thinking"),
        notes="Strong thinking at fraction of o3 cost.",
    ),
    # ── Together AI (Phase 8) ────────────────────────────────────────
    "qwen3-235b": ModelSpec(
        display="Emily \u2014 Qwen3 235B",
        provider="together",
        model_id="Qwen/Qwen3-235B-Instruct",
        context=128_000,
        thinking=True,
        input_usd=1.30,
        output_usd=4.00,
        speed="medium",
        tier="excellent",
        open_weights=True,
        license="Apache-2.0",
        best_for=("multilingual", "coding", "math", "self-hostable"),
        notes="90%+ frontier quality. 119 languages. Fully permissive.",
    ),
    "llama-4-maverick": ModelSpec(
        display="Emily \u2014 Llama Maverick",
        provider="together",
        model_id="meta-llama/llama-4-maverick",
        context=1_000_000,
        vision=True,
        input_usd=0.50,
        output_usd=1.50,
        speed="fast",
        tier="very-good",
        open_weights=True,
        best_for=("multimodal open-source", "cost-efficient vision"),
    ),
    # ── Mistral — EU / GDPR (Phase 8) ───────────────────────────────
    "mistral-large-3": ModelSpec(
        display="Emily \u2014 Mistral",
        provider="mistral",
        model_id="mistral-large-latest",
        context=128_000,
        vision=True,
        input_usd=2.00,
        output_usd=6.00,
        speed="fast",
        tier="very-good",
        best_for=("EU compliance", "GDPR-sensitive", "multilingual EU"),
    ),
    "codestral-2": ModelSpec(
        display="Emily \u2014 Codestral",
        provider="mistral",
        model_id="codestral-latest",
        context=256_000,
        input_usd=0.30,
        output_usd=0.90,
        speed="fast",
        tier="excellent",
        best_for=("code FIM", "code completion", "best dedicated code model per cost"),
    ),
    "mistral-small-3": ModelSpec(
        display="Emily \u2014 Mistral Small",
        provider="mistral",
        model_id="mistral-small-latest",
        context=32_000,
        input_usd=0.10,
        output_usd=0.30,
        speed="ultra-fast",
        tier="good",
        open_weights=True,
        license="Apache-2.0",
        best_for=("edge deployment", "mobile", "< 500ms latency"),
        notes="24B params. Runs on phones. Sub-500ms.",
    ),
    # ── OpenRouter — 300+ model pass-through (Phase 9) ───────────────
    "kimi-k2-thinking": ModelSpec(
        display="Emily \u2014 Kimi K2",
        provider="openrouter",
        model_id="moonshotai/kimi-k2-thinking",
        context=200_000,
        thinking=True,
        input_usd=0.85,
        output_usd=2.50,
        speed="medium",
        tier="excellent",
        open_weights=True,
        best_for=("math", "algorithms", "agentic tasks", "200+ tool calls"),
        notes="Near top global leaderboard for math+algorithms.",
    ),
    "glm-4-7-thinking": ModelSpec(
        display="Emily \u2014 GLM 4.7",
        provider="openrouter",
        model_id="z-ai/glm-4.7-thinking",
        context=128_000,
        thinking=True,
        input_usd=0.50,
        output_usd=1.50,
        speed="medium",
        tier="excellent",
        open_weights=True,
        license="MIT",
        best_for=("agentic benchmarks", "tool use", "terminal tasks", "self-hosting"),
        notes="42.8% HLE with tools. Outperforms many frontier models. MIT.",
    ),
    # ── OpenRouter FREE tier — zero-cost cloud models (Phase 10) ──────
    "or-free-deepseek-r1": ModelSpec(
        display="Emily \u2014 DeepSeek R1 \u2728free",
        provider="openrouter",
        model_id="deepseek/deepseek-r1-0528:free",
        context=164_000,
        thinking=True,
        input_usd=0.0,
        output_usd=0.0,
        speed="medium",
        tier="excellent",
        open_weights=True,
        license="MIT",
        best_for=("reasoning", "math", "science", "free thinking"),
        notes="DeepSeek R1 0528 on OpenRouter free tier. 20 req/min, 200/day.",
    ),
    "or-free-qwen3-235b": ModelSpec(
        display="Emily \u2014 Qwen3 235B \u2728free",
        provider="openrouter",
        model_id="qwen/qwen3-235b-a22b:free",
        context=131_000,
        thinking=True,
        input_usd=0.0,
        output_usd=0.0,
        speed="medium",
        tier="excellent",
        open_weights=True,
        license="Apache-2.0",
        best_for=("coding", "multilingual", "reasoning", "free powerhouse"),
        notes="Qwen3 235B MoE (22B active) on OpenRouter free tier.",
    ),
    "or-free-llama-70b": ModelSpec(
        display="Emily \u2014 Llama 70B \u2728free",
        provider="openrouter",
        model_id="meta-llama/llama-3.3-70b-instruct:free",
        context=128_000,
        input_usd=0.0,
        output_usd=0.0,
        speed="fast",
        tier="very-good",
        open_weights=True,
        best_for=("general chat", "multilingual", "free balanced"),
        notes="Meta Llama 3.3 70B on OpenRouter free tier. GPT-4 class.",
    ),
    "or-free-gpt-oss-120b": ModelSpec(
        display="Emily \u2014 GPT-OSS 120B \u2728free",
        provider="openrouter",
        model_id="openai/gpt-oss-120b:free",
        context=131_000,
        thinking=True,
        input_usd=0.0,
        output_usd=0.0,
        speed="medium",
        tier="excellent",
        open_weights=True,
        license="Apache-2.0",
        best_for=("agentic tasks", "tool use", "reasoning", "free frontier"),
        notes="OpenAI open-weight 120B MoE. Single H100 viable. Free tier.",
    ),
    "or-free-qwen3-vl-235b": ModelSpec(
        display="Emily \u2014 Qwen3 VL 235B \u2728free",
        provider="openrouter",
        model_id="qwen/qwen3-vl-235b-a22b:free",
        context=131_000,
        thinking=True,
        vision=True,
        input_usd=0.0,
        output_usd=0.0,
        speed="medium",
        tier="excellent",
        open_weights=True,
        best_for=("vision", "multimodal reasoning", "STEM", "free vision"),
        notes="Qwen3 VL 235B Thinking on OpenRouter free tier. Vision+reasoning.",
    ),
    # ── Ollama — additional local models (Phase 9) ──────────────────
    # Emily's config-driven models (emily-fast, emily-smart, emily-nano, etc.)
    # are registered dynamically at startup by LLMFleet._register_config_models().
    # Additional Ollama models are auto-discovered via OllamaProvider.discover_models().
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_models_for_provider(provider: str) -> dict[str, ModelSpec]:
    """Return the subset of registry entries whose *provider* matches.

    Args:
        provider: Provider key (e.g. ``"openai"``, ``"anthropic"``).

    Returns:
        A dict of ``{registry_key: ModelSpec}`` for that provider.
    """
    return {k: v for k, v in EMILY_MODEL_REGISTRY.items() if v.provider == provider}


def get_default_model() -> tuple[str, ModelSpec]:
    """Return ``(key, spec)`` for the registry entry marked ``default=True``.

    Falls back to the first entry if no default is flagged.

    Returns:
        A ``(registry_key, ModelSpec)`` tuple.
    """
    for key, spec in EMILY_MODEL_REGISTRY.items():
        if spec.default:
            return key, spec
    first_key = next(iter(EMILY_MODEL_REGISTRY))
    return first_key, EMILY_MODEL_REGISTRY[first_key]


def get_model(key: str) -> ModelSpec | None:
    """Look up a model by its registry key.

    Args:
        key: Registry key (e.g. ``"gpt-5"``).

    Returns:
        The matching :class:`ModelSpec`, or ``None``.
    """
    return EMILY_MODEL_REGISTRY.get(key)


def list_models(provider: str | None = None) -> list[ModelSpec]:
    """Return registry entries, optionally filtered by provider.

    Args:
        provider: If given, only return models from this provider.

    Returns:
        List of :class:`ModelSpec` objects.
    """
    if provider is None:
        return list(EMILY_MODEL_REGISTRY.values())
    return [v for v in EMILY_MODEL_REGISTRY.values() if v.provider == provider]


def register_dynamic_model(key: str, spec: ModelSpec) -> None:
    """Insert a dynamically created model into the registry.

    Used by Ollama auto-discovery and OpenRouter custom model creation
    to register models that aren't known at import time.

    Args:
        key: Registry key (e.g. ``"ollama-qwen3:72b"``).
        spec: The :class:`ModelSpec` to register.
    """
    EMILY_MODEL_REGISTRY[key] = spec
