"""Unit tests for security.encryption.AgeEncryption."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_pyrage():
    """Create a fake pyrage module with working encrypt/decrypt."""
    mod = MagicMock()
    # Simulate identity generation
    identity = MagicMock()
    identity.__str__ = lambda self: "AGE-SECRET-KEY-FAKE"
    recipient = MagicMock()
    identity.to_public.return_value = recipient
    mod.x25519.Identity.generate.return_value = identity
    mod.x25519.Identity.from_str.return_value = identity

    # encrypt/decrypt: XOR with 0xFF as a reversible "cipher"
    mod.encrypt = lambda data, recipients: bytes(b ^ 0xFF for b in data)
    mod.decrypt = lambda data, identities: bytes(b ^ 0xFF for b in data)

    return mod


# ---------------------------------------------------------------------------
# Tests — plaintext fallback (no backend)
# ---------------------------------------------------------------------------


class TestAgeEncryptionNoBackend:
    """When neither pyrage nor age CLI is available."""

    @patch("security.encryption._pyrage_available", return_value=False)
    @patch("security.encryption._age_cli_available", return_value=False)
    def test_non_strict_returns_plaintext(self, _cli, _py):
        from security.encryption import AgeEncryption

        enc = AgeEncryption(strict=False)
        assert not enc.is_available()

        data = b"hello world"
        assert enc.encrypt_bytes(data) == data
        assert enc.decrypt_bytes(data) == data

    @patch("security.encryption._pyrage_available", return_value=False)
    @patch("security.encryption._age_cli_available", return_value=False)
    def test_strict_raises_on_init(self, _cli, _py):
        from security.encryption import AgeEncryption

        with pytest.raises(RuntimeError, match="no backend available"):
            AgeEncryption(strict=True)


# ---------------------------------------------------------------------------
# Tests — pyrage backend
# ---------------------------------------------------------------------------


class TestAgeEncryptionPyrage:
    """When pyrage is available."""

    @patch("security.encryption._age_cli_available", return_value=False)
    @patch("security.encryption._pyrage_available", return_value=True)
    def test_is_available(self, _py, _cli):
        from security.encryption import AgeEncryption

        enc = AgeEncryption(strict=False)
        assert enc.is_available()

    @patch("security.encryption._age_cli_available", return_value=False)
    @patch("security.encryption._pyrage_available", return_value=True)
    def test_ensure_key_creates_file(self, _py, _cli, tmp_key_path: Path):
        from security.encryption import AgeEncryption

        fake_pyrage = _make_fake_pyrage()

        with patch.dict("sys.modules", {"pyrage": fake_pyrage}):
            enc = AgeEncryption(key_path=tmp_key_path, strict=False)
            key_path = enc.ensure_key()

        assert key_path.exists()
        # Key file should be readable only by owner
        assert oct(key_path.stat().st_mode)[-3:] == "600"

    @patch("security.encryption._age_cli_available", return_value=False)
    @patch("security.encryption._pyrage_available", return_value=True)
    def test_encrypt_decrypt_roundtrip(self, _py, _cli, tmp_key_path: Path):
        from security.encryption import AgeEncryption

        fake_pyrage = _make_fake_pyrage()

        with patch.dict("sys.modules", {"pyrage": fake_pyrage}):
            enc = AgeEncryption(key_path=tmp_key_path, strict=False)
            enc.ensure_key()

            plaintext = b"sensitive data"
            ciphertext = enc.encrypt_bytes(plaintext)
            assert ciphertext != plaintext  # Actually transformed

            recovered = enc.decrypt_bytes(ciphertext)
            assert recovered == plaintext

    @patch("security.encryption._age_cli_available", return_value=False)
    @patch("security.encryption._pyrage_available", return_value=True)
    def test_encrypt_decrypt_file(self, _py, _cli, tmp_key_path: Path, tmp_path: Path):
        from security.encryption import AgeEncryption

        fake_pyrage = _make_fake_pyrage()
        test_file = tmp_path / "test.txt"
        original = b"file contents here"
        test_file.write_bytes(original)

        with patch.dict("sys.modules", {"pyrage": fake_pyrage}):
            enc = AgeEncryption(key_path=tmp_key_path, strict=False)
            enc.ensure_key()

            enc.encrypt_file(test_file)
            assert test_file.read_bytes() != original  # Encrypted

            enc.decrypt_file(test_file)
            assert test_file.read_bytes() == original  # Restored

    @pytest.mark.asyncio
    @patch("security.encryption._age_cli_available", return_value=False)
    @patch("security.encryption._pyrage_available", return_value=True)
    async def test_async_encrypt_decrypt(self, _py, _cli, tmp_key_path: Path):
        from security.encryption import AgeEncryption

        fake_pyrage = _make_fake_pyrage()

        with patch.dict("sys.modules", {"pyrage": fake_pyrage}):
            enc = AgeEncryption(key_path=tmp_key_path, strict=False)
            await enc.ensure_key_async()

            plaintext = b"async sensitive"
            ciphertext = await enc.encrypt_bytes_async(plaintext)
            recovered = await enc.decrypt_bytes_async(ciphertext)
            assert recovered == plaintext
