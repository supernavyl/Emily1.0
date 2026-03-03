"""Unit tests for API auth (Bearer token and secret resolution)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import get_api_secret, require_bearer


def test_get_api_secret_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_api_secret returns EMILY_API_SECRET when set in env."""
    monkeypatch.setenv("EMILY_API_SECRET", "test-secret-123")
    with patch("api.auth.get_settings") as m:
        m.return_value.api.secret_key = None
        assert get_api_secret() == "test-secret-123"
    monkeypatch.delenv("EMILY_API_SECRET", raising=False)


def test_get_api_secret_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_api_secret returns api.secret_key when set in config."""
    monkeypatch.delenv("EMILY_API_SECRET", raising=False)
    with patch("api.auth.get_settings") as m:
        m.return_value.api.secret_key = "config-secret"
        assert get_api_secret() == "config-secret"


def test_get_api_secret_env_overrides_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config is checked first; env is used when config is None."""
    monkeypatch.setenv("EMILY_API_SECRET", "env-secret")
    with patch("api.auth.get_settings") as m:
        m.return_value.api.secret_key = None
        assert get_api_secret() == "env-secret"
    monkeypatch.delenv("EMILY_API_SECRET", raising=False)


def test_get_api_secret_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_api_secret returns None when neither config nor env set."""
    monkeypatch.delenv("EMILY_API_SECRET", raising=False)
    with patch("api.auth.get_settings") as m:
        m.return_value.api.secret_key = None
        assert get_api_secret() is None


def test_require_bearer_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """require_bearer passes when Bearer token matches secret."""
    with patch("api.auth.get_api_secret", return_value="secret"):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="secret")
        require_bearer(creds)  # no raise


def test_require_bearer_no_secret_configured() -> None:
    """require_bearer raises 503 when no API secret is configured."""
    with patch("api.auth.get_api_secret", return_value=None):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="any")
        with pytest.raises(HTTPException) as exc_info:
            require_bearer(creds)
        assert exc_info.value.status_code == 503


def test_require_bearer_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """require_bearer raises 401 when token does not match."""
    with patch("api.auth.get_api_secret", return_value="correct-secret"):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")
        with pytest.raises(HTTPException) as exc_info:
            require_bearer(creds)
        assert exc_info.value.status_code == 401


def test_require_bearer_none_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """require_bearer raises 401 when credentials are None (no header)."""
    with patch("api.auth.get_api_secret", return_value="secret"):
        with pytest.raises(HTTPException) as exc_info:
            require_bearer(None)
        assert exc_info.value.status_code == 401
