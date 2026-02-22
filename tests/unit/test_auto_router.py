"""Tests for EmilyAutoRouter — routing decisions, classification, cost estimation."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from emily_chat.emily.skills import EmilySkill
from emily_chat.models.auto_router import (
    EmilyAutoRouter,
    RoutingRequest,
    classify_request,
    estimate_cost,
    first_available,
)
from emily_chat.models.registry import EMILY_MODEL_REGISTRY, ModelSpec


@pytest.fixture()
def router() -> EmilyAutoRouter:
    """Return a fresh router instance."""
    return EmilyAutoRouter()


def _all_keys_available() -> dict[str, str]:
    """Return env vars that make all providers appear available."""
    return {
        "OPENAI_API_KEY": "sk-test",
        "ANTHROPIC_API_KEY": "sk-test",
        "GOOGLE_API_KEY": "test",
        "GROQ_API_KEY": "gsk-test",
        "XAI_API_KEY": "xai-test",
        "DEEPSEEK_API_KEY": "test",
        "TOGETHER_API_KEY": "test",
        "MISTRAL_API_KEY": "test",
        "OPENROUTER_API_KEY": "test",
    }


class TestClassifyRequest:
    """Tests for classify_request heuristics."""

    def test_math_detected(self) -> None:
        req = classify_request("Solve this integral for me")
        assert req.is_math_or_logic is True

    def test_code_detected(self) -> None:
        req = classify_request("Write a Python function to sort a list")
        assert req.is_code_request is True

    def test_creative_detected(self) -> None:
        req = classify_request("Write a short story about a dragon")
        assert req.is_creative is True

    def test_non_english_detected(self) -> None:
        req = classify_request("Переведи этот текст на английский")
        assert req.is_non_english is True

    def test_chinese_detected(self) -> None:
        req = classify_request("请帮我翻译这段话")
        assert req.is_non_english is True

    def test_plain_text_no_flags(self) -> None:
        req = classify_request("What is the weather like today?")
        assert req.is_math_or_logic is False
        assert req.is_code_request is False
        assert req.is_creative is False
        assert req.is_non_english is False

    def test_skill_overrides_code(self) -> None:
        skill = EmilySkill(name="Code", icon="", description="")
        req = classify_request("Hello", skill)
        assert req.is_code_request is True

    def test_skill_overrides_thinking(self) -> None:
        skill = EmilySkill(name="Deep Think", icon="", description="", enable_thinking=True)
        req = classify_request("Hello", skill)
        assert req.thinking_enabled is True
        assert req.is_math_or_logic is True

    def test_skill_overrides_creative(self) -> None:
        skill = EmilySkill(name="Writing", icon="", description="")
        req = classify_request("Hello", skill)
        assert req.is_creative is True

    def test_skill_overrides_translate(self) -> None:
        skill = EmilySkill(name="Translate", icon="", description="")
        req = classify_request("Hello", skill)
        assert req.is_non_english is True

    def test_multiple_flags(self) -> None:
        req = classify_request("Write a Python function that solves an equation")
        assert req.is_code_request is True
        assert req.is_math_or_logic is True


class TestEstimateCost:
    """Tests for estimate_cost."""

    def test_zero_tokens(self) -> None:
        spec = EMILY_MODEL_REGISTRY["gpt-5"]
        assert estimate_cost(spec, 0, 0) == 0.0

    def test_known_model(self) -> None:
        spec = EMILY_MODEL_REGISTRY["gpt-5"]
        cost = estimate_cost(spec, 1_000_000, 1_000_000)
        assert cost == pytest.approx(spec.input_usd + spec.output_usd, abs=0.01)

    def test_cheap_model(self) -> None:
        spec = EMILY_MODEL_REGISTRY["gemini-3-flash"]
        cost = estimate_cost(spec, 1000, 1000)
        assert cost < 0.001

    def test_free_model(self) -> None:
        spec = EMILY_MODEL_REGISTRY["ollama-local"]
        assert estimate_cost(spec, 100_000, 100_000) == 0.0


class TestFirstAvailable:
    """Tests for first_available."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_returns_first_with_key(self) -> None:
        result = first_available(["gpt-5"])
        assert result is not None
        assert result.provider == "openai"

    @patch.dict(os.environ, {}, clear=True)
    def test_returns_none_when_no_keys(self) -> None:
        result = first_available(["gpt-5", "gpt-4o"])
        assert result is None

    def test_ollama_always_available(self) -> None:
        result = first_available(["ollama-local"])
        assert result is not None


class TestRouterDecisions:
    """Tests for the routing decision tree with 20+ prompt types."""

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_math_routes_to_reasoning(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(is_math_or_logic=True)
        spec = router.route(req)
        assert spec.thinking or "math" in " ".join(spec.best_for).lower()

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_code_routes_to_code_model(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(is_code_request=True)
        spec = router.route(req)
        assert "code" in " ".join(spec.best_for).lower() or spec.provider in ("mistral", "deepseek")

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_creative_routes_to_creative_model(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(is_creative=True)
        spec = router.route(req)
        provider_ok = spec.provider in ("xai", "openai", "google")
        best_for_ok = any(w in " ".join(spec.best_for).lower() for w in ("creative", "writing", "storytelling"))
        assert provider_ok or best_for_ok

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_non_english_routes_to_multilingual(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(is_non_english=True)
        spec = router.route(req)
        assert any(w in " ".join(spec.best_for).lower() for w in ("multilingual", "eu"))

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_large_context_routes_to_big_window(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(context_tokens=600_000)
        spec = router.route(req)
        assert spec.context >= 500_000

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_video_routes_to_video_model(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(has_video=True)
        spec = router.route(req)
        assert spec.video or spec.provider in ("google", "openai")

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_image_routes_to_vision_model(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(has_image=True)
        spec = router.route(req)
        assert spec.vision

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_speed_priority(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(priority="speed")
        spec = router.route(req)
        assert spec.speed in ("blazing", "ultra-fast", "fast")

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_cost_priority(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(priority="cost")
        spec = router.route(req)
        assert spec.input_usd <= 1.0

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_quality_priority(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(priority="quality")
        spec = router.route(req)
        assert spec.tier in ("best", "best-multimodal", "best-reasoning", "excellent")

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_eu_hosting(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(require_eu_hosting=True)
        spec = router.route(req)
        assert spec.provider == "mistral"

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_agentic_routes_to_tool_use(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(estimated_tool_calls=10)
        spec = router.route(req)
        assert any(w in " ".join(spec.best_for).lower() for w in ("agentic", "tool"))

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_thinking_math_combined(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest(thinking_enabled=True, is_math_or_logic=True)
        spec = router.route(req)
        assert spec.thinking

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_balanced_default(self, router: EmilyAutoRouter) -> None:
        req = RoutingRequest()
        spec = router.route(req)
        assert spec is not None
        assert isinstance(spec, ModelSpec)

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_classify_and_route_math(self, router: EmilyAutoRouter) -> None:
        req = classify_request("Prove that sqrt(2) is irrational")
        spec = router.route(req)
        assert spec is not None

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_classify_and_route_code(self, router: EmilyAutoRouter) -> None:
        req = classify_request("Debug this Python function for me")
        spec = router.route(req)
        assert spec is not None

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_classify_and_route_creative(self, router: EmilyAutoRouter) -> None:
        req = classify_request("Write a poem about the ocean")
        spec = router.route(req)
        assert spec is not None

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_classify_and_route_translation(self, router: EmilyAutoRouter) -> None:
        req = classify_request("Translate this to French: Hello world")
        assert req.is_non_english is False  # no non-english chars

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_classify_and_route_algorithm(self, router: EmilyAutoRouter) -> None:
        req = classify_request("Implement a binary search algorithm")
        spec = router.route(req)
        assert spec is not None

    @patch.dict(os.environ, _all_keys_available(), clear=True)
    def test_classify_and_route_casual(self, router: EmilyAutoRouter) -> None:
        req = classify_request("Hey, how are you?")
        spec = router.route(req)
        assert spec is not None

    def test_fallback_always_returns(self, router: EmilyAutoRouter) -> None:
        with patch.dict(os.environ, {}, clear=True):
            req = RoutingRequest()
            spec = router.route(req)
            assert spec is not None
