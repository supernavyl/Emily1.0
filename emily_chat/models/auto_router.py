"""Intelligent auto-router for optimal model selection.

``EmilyAutoRouter`` inspects the user's request, active skill, and
available models to select the best-fit LLM automatically.  The decision
tree follows a priority chain: context size -> video -> image -> thinking
-> math/logic -> code -> creative -> non-English -> EU/GDPR -> agentic
-> speed -> cost -> balanced default.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from emily_chat.emily.skills import EmilySkill
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, ModelSpec

_MATH_PATTERNS = re.compile(
    r"\b(solve|proof|prove|theorem|integral|derivative|equations?|math|"
    r"calculus|algebra|compute|factorial|eigenvalue|matrix|probability|"
    r"statistics|logarithm|polynomial|trigonometry)\b",
    re.IGNORECASE,
)

_CODE_PATTERNS = re.compile(
    r"\b(code|program|function|class|debug|refactor|implement|algorithm|"
    r"compile|syntax|variable|loop|recursion|api|endpoint|sql|regex|"
    r"python|javascript|typescript|rust|golang|java|cpp|html|css|"
    r"react|django|flask|fastapi|docker|kubernetes|git)\b",
    re.IGNORECASE,
)

_CREATIVE_PATTERNS = re.compile(
    r"\b(write|story|poem|novel|essay|creative|fiction|character|plot|"
    r"dialogue|narrative|screenplay|lyrics|compose|blog|article|"
    r"metaphor|tone|humor|joke|funny|witty|sarcasm)\b",
    re.IGNORECASE,
)

_NON_ENGLISH_PATTERNS = re.compile(
    r"[\u0400-\u04ff\u0600-\u06ff\u3000-\u9fff\uac00-\ud7af"
    r"\u3040-\u309f\u30a0-\u30ff\u0e00-\u0e7f\u0900-\u097f]",
)


@dataclass
class RoutingRequest:
    """Describes what the user is asking for, used by the router.

    Attributes:
        text: The user's message text.
        context_tokens: Estimated current context token count.
        has_image: Whether the input contains images.
        has_video: Whether the input contains video.
        thinking_enabled: Whether thinking mode is active.
        priority: Routing priority hint.
        is_math_or_logic: Detected math/logic content.
        is_code_request: Detected code-related content.
        is_creative: Detected creative writing.
        is_non_english: Detected non-English content.
        estimated_tool_calls: Expected number of tool invocations.
        require_eu_hosting: Whether GDPR/EU hosting is required.
    """

    text: str = ""
    context_tokens: int = 0
    has_image: bool = False
    has_video: bool = False
    thinking_enabled: bool = False
    priority: str = "balanced"
    is_math_or_logic: bool = False
    is_code_request: bool = False
    is_creative: bool = False
    is_non_english: bool = False
    estimated_tool_calls: int = 0
    require_eu_hosting: bool = False


def classify_request(text: str, skill: EmilySkill | None = None) -> RoutingRequest:
    """Classify user text into a routing request using keyword heuristics.

    Args:
        text: The user's message.
        skill: Optional active skill that may override detection.

    Returns:
        A populated :class:`RoutingRequest`.
    """
    req = RoutingRequest(text=text)

    if _MATH_PATTERNS.search(text):
        req.is_math_or_logic = True
    if _CODE_PATTERNS.search(text):
        req.is_code_request = True
    if _CREATIVE_PATTERNS.search(text):
        req.is_creative = True
    if _NON_ENGLISH_PATTERNS.search(text):
        req.is_non_english = True

    if skill:
        if skill.enable_thinking:
            req.thinking_enabled = True
        if skill.name == "Code":
            req.is_code_request = True
        elif skill.name == "Deep Think":
            req.thinking_enabled = True
            req.is_math_or_logic = True
        elif skill.name in ("Writing", "Brainstorm"):
            req.is_creative = True
        elif skill.name == "Translate":
            req.is_non_english = True

    return req


def estimate_cost(
    model: ModelSpec,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate the cost of a generation in USD.

    Args:
        model: The model specification.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Estimated cost in USD.
    """
    return (
        model.input_usd * input_tokens / 1_000_000
        + model.output_usd * output_tokens / 1_000_000
    )


def _has_api_key(provider: str) -> bool:
    """Check if an API key is configured for a provider.

    Args:
        provider: Provider name (e.g. ``"openai"``).

    Returns:
        ``True`` if the relevant environment variable is set.
    """
    env_map = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "google": "GOOGLE_API_KEY",
        "groq": "GROQ_API_KEY",
        "xai": "XAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "together": "TOGETHER_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "ollama": "OLLAMA_HOST",
    }
    key = env_map.get(provider)
    if key is None:
        return False
    if provider == "ollama":
        return True
    return bool(os.environ.get(key))


def first_available(candidates: list[str]) -> ModelSpec | None:
    """Return the first model whose API key is configured.

    Args:
        candidates: List of registry keys to check.

    Returns:
        The first available :class:`ModelSpec`, or ``None``.
    """
    for key in candidates:
        spec = EMILY_MODEL_REGISTRY.get(key)
        if spec and _has_api_key(spec.provider):
            return spec
    return None


class EmilyAutoRouter:
    """Intelligent model selector based on request classification.

    Uses a decision tree to pick the optimal model from available
    candidates, considering request type, active skill, and provider
    availability.
    """

    def route(self, request: RoutingRequest) -> ModelSpec:
        """Select the optimal model for a routing request.

        Args:
            request: The classified routing request.

        Returns:
            The selected :class:`ModelSpec`.
        """
        if request.context_tokens > 500_000:
            result = first_available([
                "gemini-3-pro", "gemini-3-flash", "llama-4-scout",
                "gemini-2-5-pro",
            ])
            if result:
                return result

        if request.has_video:
            result = first_available(["gemini-3-pro", "gpt-5-2"])
            if result:
                return result

        if request.has_image:
            result = first_available([
                "gemini-3-pro", "gpt-5", "gpt-4o", "grok-4-1",
                "llama-4-maverick",
            ])
            if result:
                return result

        if request.thinking_enabled and request.is_math_or_logic:
            result = first_available([
                "o3", "deepseek-r2", "gemini-3-pro", "groq-deepseek-r1",
                "o4-mini",
            ])
            if result:
                return result

        if request.is_math_or_logic:
            result = first_available([
                "o4-mini", "o3", "deepseek-r2", "gemini-3-flash",
            ])
            if result:
                return result

        if request.is_code_request:
            result = first_available([
                "codestral-2", "deepseek-v3-2", "o4-mini",
                "gemini-3-flash",
            ])
            if result:
                return result

        if request.is_creative:
            result = first_available([
                "grok-4-1", "gpt-5-2", "gpt-5", "gemini-3-pro",
            ])
            if result:
                return result

        if request.is_non_english:
            result = first_available([
                "qwen3-235b", "qwen3-72b", "mistral-large-3",
                "gemini-3-flash",
            ])
            if result:
                return result

        if request.require_eu_hosting:
            result = first_available([
                "mistral-large-3", "mistral-small-3",
            ])
            if result:
                return result

        if request.estimated_tool_calls > 5:
            result = first_available([
                "kimi-k2-thinking", "glm-4-7-thinking", "o4-mini",
            ])
            if result:
                return result

        if request.priority == "speed":
            result = first_available([
                "groq-llama-70b", "gemini-3-flash", "mistral-small-3",
            ])
            if result:
                return result

        if request.priority == "cost":
            result = first_available([
                "gemini-3-flash", "mistral-small-3", "groq-llama-70b",
                "deepseek-v3-2",
            ])
            if result:
                return result

        if request.priority == "quality":
            result = first_available([
                "gpt-5-2", "gemini-3-pro", "gpt-5", "o3",
            ])
            if result:
                return result

        result = first_available([
            "gpt-5", "gemini-3-flash", "gpt-4o", "deepseek-v3-2",
            "groq-llama-70b", "ollama-local",
        ])
        if result:
            return result

        fallback = EMILY_MODEL_REGISTRY.get("ollama-local")
        if fallback is not None:
            return fallback

        _, fallback = next(iter(EMILY_MODEL_REGISTRY.items()))
        return fallback
