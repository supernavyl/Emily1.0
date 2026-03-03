"""
Emily Desktop App Settings & Configuration Dashboard.

Provides advanced customization, privacy controls, and policy acknowledgments.
"""

import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class PrivacyLevel(Enum):
    """Privacy mode settings."""

    FULL = "full"  # Collect everything
    BALANCED = "balanced"  # Standard privacy
    STRICT = "strict"  # Minimal data collection
    GUEST = "guest"  # No personal data storage


class DataRetention(Enum):
    """How long to keep data."""

    ONE_WEEK = "1week"
    ONE_MONTH = "1month"
    THREE_MONTHS = "3months"
    ONE_YEAR = "1year"
    FOREVER = "forever"


class Theme(Enum):
    """UI themes."""

    DARK = "dark"
    LIGHT = "light"
    AUTO = "auto"


@dataclass
class PrivacyPolicy:
    """Privacy policy acknowledgment."""

    accepted: bool = False
    accepted_at: float = 0.0
    version: str = "1.0"
    ip_logging: bool = False
    analytics: bool = False
    error_reporting: bool = True
    telemetry: bool = False


@dataclass
class TermsOfService:
    """Terms of service acknowledgment."""

    accepted: bool = False
    accepted_at: float = 0.0
    version: str = "1.0"


@dataclass
class SecuritySettings:
    """Security configuration."""

    password_required: bool = True
    password_hash: str = ""  # SHA-256
    session_timeout_minutes: int = 60
    require_verification_on_startup: bool = True
    auto_lock_on_inactivity: bool = True
    lock_timeout_minutes: int = 15
    failed_attempts_lockout: int = 3
    lockout_duration_minutes: int = 5


@dataclass
class DisplaySettings:
    """UI customization."""

    theme: Theme = Theme.DARK
    font_size: int = 14  # pixels
    animations_enabled: bool = True
    compact_mode: bool = False
    show_advanced_metrics: bool = False
    sidebar_collapsed: bool = False


@dataclass
class DataSettings:
    """Data collection and retention."""

    privacy_level: PrivacyLevel = PrivacyLevel.BALANCED
    data_retention: DataRetention = DataRetention.ONE_YEAR
    auto_backup: bool = True
    backup_frequency_hours: int = 24
    export_format: str = "json"  # json, csv, sqlite


@dataclass
class AdvancedSettings:
    """Advanced/power-user settings."""

    enable_debug_mode: bool = False
    enable_experimental_features: bool = False
    telemetry_verbose: bool = False
    performance_profiling: bool = False
    memory_limit_gb: int = 8
    max_concurrent_agents: int = 4
    enable_voice_logging: bool = False
    voice_log_retention_days: int = 7


@dataclass
class AppSettings:
    """Complete application settings."""

    display: DisplaySettings = field(default_factory=DisplaySettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    data: DataSettings = field(default_factory=DataSettings)
    advanced: AdvancedSettings = field(default_factory=AdvancedSettings)
    privacy_policy: PrivacyPolicy = field(default_factory=PrivacyPolicy)
    terms_of_service: TermsOfService = field(default_factory=TermsOfService)
    last_updated: float = field(default_factory=time.time)
    version: str = "1.0"


class SettingsManager:
    """Manage application settings with persistence."""

    def __init__(self, settings_path: str = "data/app_settings.json"):
        self._path = Path(settings_path)
        self._settings: AppSettings | None = None
        self._dirty = False

    async def load(self) -> AppSettings:
        """Load settings from disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        if self._path.exists():
            try:
                raw = self._path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._settings = self._deserialize(data)
                log.info("settings_loaded", path=str(self._path))
            except Exception as exc:
                log.warning("settings_load_failed", error=str(exc), using_defaults=True)
                self._settings = AppSettings()
        else:
            self._settings = AppSettings()

        return self._settings

    async def save(self) -> None:
        """Save settings to disk."""
        if self._settings is None:
            return

        self._settings.last_updated = time.time()
        data = self._serialize(self._settings)

        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self._dirty = False
        log.info("settings_saved", path=str(self._path))

    def get_settings(self) -> AppSettings:
        """Get current settings."""
        return self._settings or AppSettings()

    async def update_display(self, updates: dict[str, Any]) -> None:
        """Update display settings."""
        if self._settings is None:
            return
        for key, value in updates.items():
            if hasattr(self._settings.display, key):
                setattr(self._settings.display, key, value)
        self._dirty = True
        await self.save()

    async def update_security(self, updates: dict[str, Any]) -> None:
        """Update security settings."""
        if self._settings is None:
            return
        for key, value in updates.items():
            if hasattr(self._settings.security, key):
                setattr(self._settings.security, key, value)
        self._dirty = True
        await self.save()

    async def update_data(self, updates: dict[str, Any]) -> None:
        """Update data collection settings."""
        if self._settings is None:
            return
        for key, value in updates.items():
            if hasattr(self._settings.data, key):
                setattr(self._settings.data, key, value)
        self._dirty = True
        await self.save()

    async def update_advanced(self, updates: dict[str, Any]) -> None:
        """Update advanced settings."""
        if self._settings is None:
            return
        for key, value in updates.items():
            if hasattr(self._settings.advanced, key):
                setattr(self._settings.advanced, key, value)
        self._dirty = True
        await self.save()

    async def accept_privacy_policy(self, version: str = "1.0") -> None:
        """Accept privacy policy."""
        if self._settings is None:
            return
        self._settings.privacy_policy.accepted = True
        self._settings.privacy_policy.accepted_at = time.time()
        self._settings.privacy_policy.version = version
        self._dirty = True
        await self.save()
        log.info("privacy_policy_accepted", version=version)

    async def accept_terms_of_service(self, version: str = "1.0") -> None:
        """Accept terms of service."""
        if self._settings is None:
            return
        self._settings.terms_of_service.accepted = True
        self._settings.terms_of_service.accepted_at = time.time()
        self._settings.terms_of_service.version = version
        self._dirty = True
        await self.save()
        log.info("terms_accepted", version=version)

    def _serialize(self, settings: AppSettings) -> dict:
        """Convert settings to dict."""
        return {
            "display": asdict(settings.display) | {"theme": settings.display.theme.value},
            "security": asdict(settings.security),
            "data": asdict(settings.data)
            | {
                "privacy_level": settings.data.privacy_level.value,
                "data_retention": settings.data.data_retention.value,
            },
            "advanced": asdict(settings.advanced),
            "privacy_policy": asdict(settings.privacy_policy),
            "terms_of_service": asdict(settings.terms_of_service),
            "last_updated": settings.last_updated,
            "version": settings.version,
        }

    def _deserialize(self, data: dict) -> AppSettings:
        """Convert dict to settings."""
        return AppSettings(
            display=DisplaySettings(
                theme=Theme(data.get("display", {}).get("theme", "dark")),
                font_size=data.get("display", {}).get("font_size", 14),
                animations_enabled=data.get("display", {}).get("animations_enabled", True),
                compact_mode=data.get("display", {}).get("compact_mode", False),
                show_advanced_metrics=data.get("display", {}).get("show_advanced_metrics", False),
                sidebar_collapsed=data.get("display", {}).get("sidebar_collapsed", False),
            ),
            security=SecuritySettings(**data.get("security", {})),
            data=DataSettings(
                privacy_level=PrivacyLevel(data.get("data", {}).get("privacy_level", "balanced")),
                data_retention=DataRetention(data.get("data", {}).get("data_retention", "1year")),
                **{
                    k: v
                    for k, v in data.get("data", {}).items()
                    if k not in ["privacy_level", "data_retention"]
                },
            ),
            advanced=AdvancedSettings(**data.get("advanced", {})),
            privacy_policy=PrivacyPolicy(**data.get("privacy_policy", {})),
            terms_of_service=TermsOfService(**data.get("terms_of_service", {})),
            last_updated=data.get("last_updated", time.time()),
            version=data.get("version", "1.0"),
        )
