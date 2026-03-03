"""Unit tests for security/vault/."""

from __future__ import annotations

import pytest
import pytest_asyncio

from security.vault.crypto import VaultCrypto
from security.vault.health_checker import PasswordStrengthScorer, VaultHealthChecker
from security.vault.models import Credential, CredentialSummary, CredentialType
from security.vault.totp import TOTPProvider
from security.vault.vault import CredentialVault, VaultLockedError

MASTER = "correct-horse-battery-staple-test"


@pytest_asyncio.fixture
async def vault(tmp_path):
    """Provide an unlocked CredentialVault backed by a temp file."""
    v = CredentialVault(
        db_path=str(tmp_path / "vault.db"),
        auto_lock_minutes=60,
        audit_log_path=str(tmp_path / "vault_audit.log"),
    )
    await v.unlock(MASTER)
    yield v
    await v.close()


# ---------------------------------------------------------------------------
# Crypto tests
# ---------------------------------------------------------------------------


def test_derive_key_deterministic() -> None:
    """Same master password + salt always produces the same key."""
    crypto = VaultCrypto()
    salt = b"test_salt_exactly_32_bytes_long!"
    k1 = crypto.derive_key("my-password", salt)
    k2 = crypto.derive_key("my-password", salt)
    assert bytes(k1) == bytes(k2)
    crypto.zero_key(k1)
    crypto.zero_key(k2)


def test_zero_key_clears_memory() -> None:
    """zero_key overwrites the bytearray with zeros."""
    crypto = VaultCrypto()
    salt = b"test_salt_exactly_32_bytes_long!"
    key = crypto.derive_key("my-password", salt)
    assert any(b != 0 for b in key)
    crypto.zero_key(key)
    assert all(b == 0 for b in key)


def test_encrypt_decrypt_roundtrip() -> None:
    """Plaintext survives encrypt → decrypt roundtrip."""
    crypto = VaultCrypto()
    salt = b"test_salt_exactly_32_bytes_long!"
    key = crypto.derive_key("hunter2", salt)
    try:
        ciphertext = crypto.encrypt_hex(key, "s3cr3t-p4ssw0rd!")
        assert ciphertext != "s3cr3t-p4ssw0rd!"
        plaintext = crypto.decrypt_hex(key, ciphertext)
        assert plaintext == "s3cr3t-p4ssw0rd!"
    finally:
        crypto.zero_key(key)


def test_different_nonce_each_encrypt() -> None:
    """Two encryptions of the same plaintext produce different ciphertexts (random nonce)."""
    crypto = VaultCrypto()
    salt = b"test_salt_exactly_32_bytes_long!"
    key = crypto.derive_key("pw", salt)
    try:
        c1 = crypto.encrypt_hex(key, "same text")
        c2 = crypto.encrypt_hex(key, "same text")
        assert c1 != c2
    finally:
        crypto.zero_key(key)


def test_wrong_key_fails_decryption() -> None:
    """Decrypting with the wrong key raises an error."""
    crypto = VaultCrypto()
    salt = b"test_salt_exactly_32_bytes_long!"
    key1 = crypto.derive_key("password1", salt)
    key2 = crypto.derive_key("password2", salt)
    try:
        ciphertext = crypto.encrypt_hex(key1, "secret")
        with pytest.raises(Exception):
            crypto.decrypt_hex(key2, ciphertext)
    finally:
        crypto.zero_key(key1)
        crypto.zero_key(key2)


# ---------------------------------------------------------------------------
# Vault CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vault_add_and_get(vault: CredentialVault) -> None:
    """Added credential can be retrieved with plaintext secret."""
    cred = Credential(
        type=CredentialType.PASSWORD,
        name="Gmail Work",
        service="gmail.com",
        username="alice@gmail.com",
    )
    cred_id = await vault.add(cred, plaintext_secret="hunter2")

    retrieved = await vault.get(cred_id)
    assert retrieved.secret == "hunter2"
    assert retrieved.username == "alice@gmail.com"
    assert retrieved.name == "Gmail Work"


@pytest.mark.asyncio
async def test_vault_secret_not_plaintext_in_db(vault: CredentialVault, tmp_path) -> None:
    """The raw database row does NOT contain the plaintext secret."""
    import aiosqlite

    cred = Credential(name="Test", service="example.com", username="user")
    await vault.add(cred, plaintext_secret="plaintext-secret")

    db_path = str(tmp_path / "vault.db")
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT secret FROM credentials WHERE id = ?", (cred.id,)) as cur:
            row = await cur.fetchone()
    assert row is not None
    assert "plaintext-secret" not in row[0]


@pytest.mark.asyncio
async def test_vault_search_returns_no_secrets(vault: CredentialVault) -> None:
    """Search results are summaries — they never expose the secret field."""
    cred = Credential(name="GitHub", service="github.com", username="dev")
    await vault.add(cred, plaintext_secret="ghp_supersecrettoken")

    results = await vault.search("GitHub")
    assert len(results) > 0
    summary = results[0]
    assert isinstance(summary, CredentialSummary)
    # CredentialSummary has no `secret` attribute
    assert not hasattr(summary, "secret")


@pytest.mark.asyncio
async def test_vault_soft_delete(vault: CredentialVault) -> None:
    """Deleted credentials do not appear in search results."""
    cred = Credential(name="ToBeDel", service="del.example.com", username="u")
    cred_id = await vault.add(cred, plaintext_secret="xyz")

    await vault.delete(cred_id)
    results = await vault.search("ToBeDel")
    assert all(r.id != cred_id for r in results)


@pytest.mark.asyncio
async def test_vault_locked_raises(tmp_path) -> None:
    """Operations on a locked vault raise VaultLockedError."""
    v = CredentialVault(
        db_path=str(tmp_path / "vault2.db"),
        audit_log_path=str(tmp_path / "a.log"),
    )
    await v.unlock(MASTER)
    await v.lock()

    with pytest.raises(VaultLockedError):
        await v.search("anything")


@pytest.mark.asyncio
async def test_generate_password_length(vault: CredentialVault) -> None:
    """Generated passwords have the requested length."""
    pw = await vault.generate_password(length=32)
    assert len(pw) == 32


@pytest.mark.asyncio
async def test_generate_password_minimum_length(vault: CredentialVault) -> None:
    """Password generator enforces minimum length of 12."""
    pw = await vault.generate_password(length=4)
    assert len(pw) >= 12


# ---------------------------------------------------------------------------
# TOTP tests
# ---------------------------------------------------------------------------


def test_totp_generate_code() -> None:
    """TOTPProvider generates a 6-digit code from a valid seed."""
    totp = TOTPProvider()
    import pyotp

    seed = pyotp.random_base32()
    code = totp.get_code(seed)
    assert len(code) == 6
    assert code.isdigit()


def test_totp_verify() -> None:
    """Generated TOTP code verifies correctly."""
    totp = TOTPProvider()
    import pyotp

    seed = pyotp.random_base32()
    code = totp.get_code(seed)
    assert totp.verify(seed, code)


def test_totp_invalid_seed_raises() -> None:
    """Invalid TOTP seed raises ValueError."""
    totp = TOTPProvider()
    with pytest.raises((ValueError, Exception)):
        totp.get_code("not-valid-base32!!!")


# ---------------------------------------------------------------------------
# Health checker tests
# ---------------------------------------------------------------------------


def test_password_scorer_strong() -> None:
    """Strong passwords score high."""
    scorer = PasswordStrengthScorer()
    score = scorer.score("Tr0ub4dor&3-CorrectorHorse!")
    assert score > 0.7


def test_password_scorer_weak() -> None:
    """Short simple passwords score low."""
    scorer = PasswordStrengthScorer()
    score = scorer.score("abc")
    assert score < 0.4


def test_password_scorer_empty() -> None:
    """Empty password scores zero."""
    scorer = PasswordStrengthScorer()
    assert scorer.score("") == 0.0


def test_health_checker_expiring() -> None:
    """VaultHealthChecker flags credentials expiring within the window."""
    from datetime import date, timedelta

    checker = VaultHealthChecker()
    soon = (date.today() + timedelta(days=5)).isoformat()
    summaries = [
        CredentialSummary(
            id="1",
            type=CredentialType.PASSWORD,
            name="Expiring Soon",
            service="s",
            username="u",
            url="",
            tags=[],
            created_at="",
            updated_at="",
            last_accessed="",
            password_strength=0.9,
            expiry_date=soon,
            associated_entity_ids=[],
        )
    ]
    alerts = checker.check_expiring(summaries, warn_days=30)
    assert len(alerts) == 1
    assert alerts[0].alert_type == "expiring"


def test_health_checker_expired() -> None:
    """VaultHealthChecker flags already-expired credentials as critical."""
    from datetime import date, timedelta

    checker = VaultHealthChecker()
    past = (date.today() - timedelta(days=10)).isoformat()
    summaries = [
        CredentialSummary(
            id="2",
            type=CredentialType.PASSWORD,
            name="Expired Key",
            service="s",
            username="u",
            url="",
            tags=[],
            created_at="",
            updated_at="",
            last_accessed="",
            password_strength=0.5,
            expiry_date=past,
            associated_entity_ids=[],
        )
    ]
    alerts = checker.check_expiring(summaries)
    assert len(alerts) == 1
    assert alerts[0].severity == "critical"
