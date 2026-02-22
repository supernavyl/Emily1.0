"""Tests for sidebar pure-logic helpers (no Qt dependency required)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from emily_chat.storage.models import ConversationSummary
from emily_chat.ui.left_sidebar import (
    PROVIDER_COLORS,
    group_conversations,
    relative_time,
)


def _make_conv(
    title: str = "Test",
    updated_at: datetime | None = None,
    pinned: bool = False,
    provider: str | None = None,
) -> ConversationSummary:
    now = updated_at or datetime.now(timezone.utc)
    return ConversationSummary(
        id=title.lower().replace(" ", "_"),
        title=title,
        created_at=now,
        updated_at=now,
        pinned=pinned,
        provider=provider,
    )


# ------------------------------------------------------------------
# group_conversations
# ------------------------------------------------------------------


class TestGroupConversations:
    def test_empty_list(self) -> None:
        groups = group_conversations([])
        assert len(groups) == 0

    def test_pinned_appears_first(self) -> None:
        now = datetime.now(timezone.utc)
        convs = [
            _make_conv("Normal", updated_at=now),
            _make_conv("Pinned", updated_at=now - timedelta(days=10), pinned=True),
        ]
        groups = group_conversations(convs)
        labels = list(groups.keys())
        assert labels[0] == "PINNED"
        assert groups["PINNED"][0].title == "Pinned"

    def test_today_bucket(self) -> None:
        now = datetime.now(timezone.utc)
        convs = [_make_conv("Recent", updated_at=now - timedelta(minutes=30))]
        groups = group_conversations(convs)
        assert "TODAY" in groups
        assert groups["TODAY"][0].title == "Recent"

    def test_yesterday_bucket(self) -> None:
        yesterday = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(hours=6)
        convs = [_make_conv("Yesterday chat", updated_at=yesterday)]
        groups = group_conversations(convs)
        assert "YESTERDAY" in groups

    def test_older_buckets_use_month_year(self) -> None:
        old = datetime(2024, 6, 15, tzinfo=timezone.utc)
        convs = [_make_conv("Old one", updated_at=old)]
        groups = group_conversations(convs)
        assert "June 2024" in groups

    def test_pinned_conversation_not_in_date_bucket(self) -> None:
        now = datetime.now(timezone.utc)
        convs = [_make_conv("Pinned today", updated_at=now, pinned=True)]
        groups = group_conversations(convs)
        assert "PINNED" in groups
        assert "TODAY" not in groups


# ------------------------------------------------------------------
# relative_time
# ------------------------------------------------------------------


class TestRelativeTime:
    def test_just_now(self) -> None:
        assert relative_time(datetime.now(timezone.utc)) == "just now"

    def test_minutes_ago(self) -> None:
        t = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert relative_time(t) == "5m ago"

    def test_hours_ago(self) -> None:
        t = datetime.now(timezone.utc) - timedelta(hours=3)
        assert relative_time(t) == "3h ago"

    def test_yesterday(self) -> None:
        t = datetime.now(timezone.utc) - timedelta(hours=30)
        assert relative_time(t) == "Yesterday"

    def test_days_ago(self) -> None:
        t = datetime.now(timezone.utc) - timedelta(days=4)
        assert relative_time(t) == "4d ago"

    def test_older_uses_date(self) -> None:
        t = datetime(2024, 1, 15, tzinfo=timezone.utc)
        result = relative_time(t)
        assert "Jan" in result and "15" in result

    def test_naive_datetime_handled(self) -> None:
        """Naive (no tzinfo) datetimes should not crash; they're treated as UTC."""
        t = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        assert relative_time(t) == "1h ago"


# ------------------------------------------------------------------
# Provider colours
# ------------------------------------------------------------------


class TestProviderColors:
    def test_known_providers_have_colors(self) -> None:
        for provider in ("anthropic", "openai", "google", "groq", "ollama"):
            assert provider in PROVIDER_COLORS
            assert PROVIDER_COLORS[provider].startswith("#")

    def test_all_colors_are_hex(self) -> None:
        for color in PROVIDER_COLORS.values():
            assert color.startswith("#")
            assert len(color) == 7
