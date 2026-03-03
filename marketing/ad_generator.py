"""
AI-powered ad copy generator.

Takes a product description (or URL) and target audience, then uses the
LLM fleet to generate scored ad creative variations across platforms.

Flow:
  1. Parse product info (description, USPs, price, images)
  2. Generate N ad variations per platform using tiered models
  3. Score each variation with a critic prompt
  4. Return top-K creatives ranked by score

Uses QwQ-32B (smart tier) for strategic copy and Qwen3-8B (voice_fast)
for bulk variation generation — all local, zero API cost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from llm.client import ChatMessage
from llm.fleet import LLMFleet
from llm.router import ModelTier, TaskType
from marketing.platforms.base import AdCreative
from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class ProductInfo:
    """Parsed product data for ad generation."""

    name: str
    description: str
    price: str = ""
    currency: str = "USD"
    url: str = ""
    images: list[str] = field(default_factory=list)
    usps: list[str] = field(default_factory=list)
    category: str = ""
    target_audience: str = ""


@dataclass
class AdBrief:
    """Instructions for ad generation."""

    product: ProductInfo
    platforms: list[str] = field(default_factory=lambda: ["meta", "tiktok"])
    variations_per_platform: int = 5
    tone: str = "persuasive"
    cta_options: list[str] = field(
        default_factory=lambda: ["Shop Now", "Learn More", "Get Yours", "Buy Now"]
    )
    max_headline_chars: int = 40
    max_body_chars: int = 125


_GENERATE_PROMPT = """\
You are an expert direct-response copywriter specializing in {platform} ads.

PRODUCT:
Name: {name}
Description: {description}
Price: {price} {currency}
USPs: {usps}
Target Audience: {audience}

Generate exactly {n} ad variations. Each variation must have:
- headline: max {max_headline} chars, attention-grabbing, specific
- body: max {max_body} chars, benefit-driven, creates urgency
- cta: one of {ctas}

Platform-specific rules for {platform}:
- Meta: lead with a bold claim or question, use social proof language
- TikTok: casual, trend-aware, use "POV:" or "Wait for it" hooks
- Google: keyword-rich, specific benefits, include price if competitive
- YouTube: hook in first 3 words, emotionally compelling

Return ONLY a JSON array, no other text:
[{{"headline": "...", "body": "...", "cta": "..."}}]
"""

_SCORE_PROMPT = """\
You are an ad performance expert. Score each ad creative on a 0-10 scale.

Scoring criteria:
- HOOK (0-3): Does the headline stop scrolling? Is it specific, not generic?
- BENEFIT (0-3): Does the body clearly communicate value to the buyer?
- URGENCY (0-2): Does it create a reason to act now?
- CLARITY (0-2): Is the message instantly understandable?

Product context: {name} — {description}
Target audience: {audience}

Ads to score:
{ads_json}

Return ONLY a JSON array of scores (same order as input):
[{{"score": 7.5, "reasoning": "..."}}]
"""


class AdGenerator:
    """Generates and scores ad creatives using the LLM fleet."""

    def __init__(self, fleet: LLMFleet) -> None:
        self._fleet = fleet

    async def generate(self, brief: AdBrief) -> list[AdCreative]:
        """Generate scored ad creatives for all requested platforms.

        Args:
            brief: Ad generation brief with product info and platform targets.

        Returns:
            List of AdCreative objects sorted by score (highest first).
        """
        all_creatives: list[AdCreative] = []

        for platform in brief.platforms:
            log.info("generating_ads", platform=platform, n=brief.variations_per_platform)
            raw = await self._generate_for_platform(brief, platform)
            scored = await self._score_creatives(raw, brief)
            all_creatives.extend(scored)

        all_creatives.sort(key=lambda c: c.score, reverse=True)
        log.info("ad_generation_complete", total=len(all_creatives))
        return all_creatives

    async def _generate_for_platform(self, brief: AdBrief, platform: str) -> list[AdCreative]:
        """Generate ad variations for a single platform."""
        prompt = _GENERATE_PROMPT.format(
            platform=platform,
            name=brief.product.name,
            description=brief.product.description,
            price=brief.product.price,
            currency=brief.product.currency,
            usps=", ".join(brief.product.usps) or "N/A",
            audience=brief.product.target_audience or "general",
            n=brief.variations_per_platform,
            max_headline=brief.max_headline_chars,
            max_body=brief.max_body_chars,
            ctas=json.dumps(brief.cta_options),
        )

        messages = [
            ChatMessage(role="system", content="You are an expert ad copywriter."),
            ChatMessage(role="user", content=prompt),
        ]

        # Use voice_fast (8B) for bulk generation — fast and free
        result = await self._fleet.chat(
            user_message=prompt,
            messages=messages,
            task_type=TaskType.CHAT,
            force_tier=ModelTier.VOICE_FAST,
            temperature=0.9,
            max_tokens=2048,
        )

        return self._parse_creatives(result.content, platform)

    async def _score_creatives(
        self, creatives: list[AdCreative], brief: AdBrief
    ) -> list[AdCreative]:
        """Score creatives using the smart tier (QwQ-32B) as critic."""
        if not creatives:
            return []

        ads_data = [{"headline": c.headline, "body": c.body, "cta": c.cta} for c in creatives]

        prompt = _SCORE_PROMPT.format(
            name=brief.product.name,
            description=brief.product.description,
            audience=brief.product.target_audience or "general",
            ads_json=json.dumps(ads_data, indent=2),
        )

        messages = [
            ChatMessage(role="system", content="You are an ad performance analyst."),
            ChatMessage(role="user", content=prompt),
        ]

        # Use smart tier (QwQ-32B) for critical evaluation
        result = await self._fleet.chat(
            user_message=prompt,
            messages=messages,
            task_type=TaskType.ANALYSIS,
            force_tier=ModelTier.SMART,
            temperature=0.3,
            max_tokens=2048,
        )

        scores = self._parse_scores(result.content)

        for i, creative in enumerate(creatives):
            if i < len(scores):
                creative.score = scores[i].get("score", 5.0)
                creative.metadata["reasoning"] = scores[i].get("reasoning", "")

        return creatives

    @staticmethod
    def _parse_creatives(raw: str, platform: str) -> list[AdCreative]:
        """Parse JSON array of ad creatives from LLM output."""
        # Extract JSON array from response (may have surrounding text)
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            log.warning("no_json_array_in_response", raw_len=len(raw))
            return []

        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            log.warning("json_parse_failed", raw=raw[start : end + 1][:200])
            return []

        creatives = []
        for item in data:
            if isinstance(item, dict) and "headline" in item:
                creatives.append(
                    AdCreative(
                        headline=str(item.get("headline", "")),
                        body=str(item.get("body", "")),
                        cta=str(item.get("cta", "Shop Now")),
                        platform=platform,
                    )
                )
        return creatives

    @staticmethod
    def _parse_scores(raw: str) -> list[dict[str, Any]]:
        """Parse JSON array of scores from LLM output."""
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return []
