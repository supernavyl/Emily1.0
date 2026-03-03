"""Unit tests for the public get_chat_db accessor in api.app."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from api.app import get_chat_db


def test_get_chat_db_returns_none_before_startup() -> None:
    """get_chat_db returns None when the app has not started."""
    with patch("api.app._chat_db", None):
        assert get_chat_db() is None


def test_get_chat_db_returns_instance_after_startup() -> None:
    """get_chat_db returns the database instance once initialised."""
    sentinel = MagicMock(name="ConversationDatabase")
    with patch("api.app._chat_db", sentinel):
        assert get_chat_db() is sentinel
