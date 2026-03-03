"""
Abstract base for ad platform adapters.

Each platform (Meta, Google, TikTok) implements this interface so the
campaign manager can deploy, monitor, and optimize ads uniformly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AdStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class CampaignObjective(StrEnum):
    CONVERSIONS = "conversions"
    TRAFFIC = "traffic"
    ENGAGEMENT = "engagement"
    LEADS = "leads"
    SALES = "sales"
    AWARENESS = "awareness"


@dataclass
class AdCreative:
    """A single ad creative variant ready for deployment."""

    headline: str
    body: str
    cta: str = "Shop Now"
    image_url: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    platform: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CampaignConfig:
    """Platform-agnostic campaign configuration."""

    name: str
    objective: CampaignObjective
    daily_budget_usd: float
    target_audience: dict[str, Any] = field(default_factory=dict)
    creatives: list[AdCreative] = field(default_factory=list)
    start_date: str | None = None
    end_date: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AdMetrics:
    """Performance metrics for a single ad or campaign."""

    impressions: int = 0
    clicks: int = 0
    spend_usd: float = 0.0
    conversions: int = 0
    revenue_usd: float = 0.0

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions * 100) if self.impressions else 0.0

    @property
    def cpc(self) -> float:
        return (self.spend_usd / self.clicks) if self.clicks else 0.0

    @property
    def cpa(self) -> float:
        return (self.spend_usd / self.conversions) if self.conversions else 0.0

    @property
    def roas(self) -> float:
        return (self.revenue_usd / self.spend_usd) if self.spend_usd else 0.0


class PlatformAdapter(ABC):
    """Abstract interface for an ad platform."""

    platform_name: str = ""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Verify API credentials. Returns True if successful."""
        ...

    @abstractmethod
    async def create_campaign(self, config: CampaignConfig) -> str:
        """Deploy a campaign. Returns platform campaign ID."""
        ...

    @abstractmethod
    async def upload_creative(self, creative: AdCreative, campaign_id: str) -> str:
        """Upload a creative to an existing campaign. Returns creative ID."""
        ...

    @abstractmethod
    async def get_metrics(self, campaign_id: str) -> AdMetrics:
        """Fetch current performance metrics for a campaign."""
        ...

    @abstractmethod
    async def pause_campaign(self, campaign_id: str) -> bool:
        """Pause a running campaign."""
        ...

    @abstractmethod
    async def resume_campaign(self, campaign_id: str) -> bool:
        """Resume a paused campaign."""
        ...

    @abstractmethod
    async def scale_budget(self, campaign_id: str, new_daily_usd: float) -> bool:
        """Adjust the daily budget for a campaign."""
        ...
