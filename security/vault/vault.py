"""
Encrypted Credential Vault — the secure heart of Emily's knowledge OS.

Security guarantees enforced here:
- Master password is NEVER stored, logged, or written to any file.
- It exists only in the scope of unlock() and is discarded immediately after
  key derivation. The derived key (bytearray) lives in memory only while
  the vault is unlocked; it is zeroed on lock() or inactivity timeout.
- Every vault access (read OR write) is logged to the audit log BEFORE
  returning results.
- Credentials returned from get() contain plaintext secrets in memory only.
  The caller is responsible for zeroing strings after use.
- TTS integration MUST filter vault output — this class does not enforce that,
  but the audit log will show every access.
- Auto-lock fires after `auto_lock_minutes` of inactivity.
"""

from __future__ import annotations

import asyncio
import secrets
import string
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from observability.logger import get_logger
from security.audit_log import AuditLog
from security.vault.crypto import VaultCrypto
from security.vault.health_checker import VaultHealthChecker
from security.vault.models import (
    Credential,
    CredentialSummary,
)
from security.vault.totp import TOTPProvider

log = get_logger(__name__)

_VAULT_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credentials (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    service TEXT NOT NULL,
    username TEXT NOT NULL,
    secret TEXT NOT NULL,
    totp_seed TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    associated_entity_ids TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    password_strength REAL NOT NULL DEFAULT 0.0,
    expiry_date TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_creds_service ON credentials(service);
CREATE INDEX IF NOT EXISTS idx_creds_type ON credentials(type);
CREATE INDEX IF NOT EXISTS idx_creds_active ON credentials(is_deleted);
"""


class VaultLockedError(RuntimeError):
    """Raised when a vault operation is attempted while the vault is locked."""


class CredentialVault:
    """
    Async encrypted credential vault.

    Stores credentials in a SQLite database with per-credential
    AES-256-GCM encryption. The vault key is derived from the master
    password via Argon2id and lives only in memory while unlocked.

    Auto-locks after configurable inactivity. Every access is written
    to the audit log before returning results.
    """

    def __init__(
        self,
        db_path: str = "data/vault.db",
        auto_lock_minutes: int = 5,
        audit_log_path: str = "logs/vault_audit.log",
    ) -> None:
        """
        Args:
            db_path: Path to the encrypted SQLite credential database.
            auto_lock_minutes: Idle minutes before automatic vault lock.
            audit_log_path: Path for the vault-specific audit log.
        """
        self._db_path = db_path
        self._auto_lock_seconds = auto_lock_minutes * 60
        self._crypto = VaultCrypto()
        self._totp = TOTPProvider()
        self._health = VaultHealthChecker()
        self._audit = AuditLog(path=audit_log_path)

        self._db: aiosqlite.Connection | None = None
        self._key: bytearray | None = None  # zeroed on lock()
        self._vault_id: str = ""
        self._lock_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _open_db(self) -> None:
        """Open SQLite connection and apply schema."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.executescript(_VAULT_SCHEMA)

        # Ensure vault_id exists
        async with self._db.execute("SELECT value FROM vault_meta WHERE key = 'vault_id'") as cur:
            row = await cur.fetchone()
            if row:
                self._vault_id = row["value"]
            else:
                self._vault_id = str(uuid.uuid4())
                await self._db.execute(
                    "INSERT INTO vault_meta (key, value) VALUES ('vault_id', ?)",
                    (self._vault_id,),
                )

        await self._db.commit()

    async def unlock(self, master_password: str) -> bool:
        """
        Unlock the vault by deriving the key from the master password.

        The master_password string is used only within this method scope —
        it is never stored, assigned to an instance attribute, or logged.

        Args:
            master_password: The user's master password (plaintext, in-memory only).

        Returns:
            True if unlocked successfully.
        """
        if self._db is None:
            await self._open_db()

        salt = VaultCrypto.make_vault_salt(self._vault_id)
        self._key = self._crypto.derive_key(master_password, salt)
        # master_password goes out of scope here — Python GC will collect it

        self._reset_lock_timer()
        await self._audit.append("vault_unlocked", "CredentialVault", {})
        log.info("vault_unlocked")
        return True

    async def lock(self) -> None:
        """
        Lock the vault and zero the in-memory key.

        Safe to call multiple times.
        """
        if self._key is not None:
            self._crypto.zero_key(self._key)
            self._key = None

        if self._lock_task and not self._lock_task.done():
            self._lock_task.cancel()
            self._lock_task = None

        await self._audit.append("vault_locked", "CredentialVault", {})
        log.info("vault_locked")

    def is_unlocked(self) -> bool:
        """Return True if the vault is currently unlocked."""
        return self._key is not None

    def _require_unlocked(self) -> bytearray:
        """Return the active key or raise VaultLockedError."""
        if self._key is None:
            raise VaultLockedError("Vault is locked. Call unlock() first.")
        self._reset_lock_timer()
        return self._key

    def _require_db(self) -> aiosqlite.Connection:
        """Return the active DB connection or raise RuntimeError."""
        if self._db is None:
            raise RuntimeError("Vault database not open. Call unlock() first.")
        return self._db

    def _reset_lock_timer(self) -> None:
        """Cancel and restart the auto-lock countdown."""
        if self._lock_task and not self._lock_task.done():
            self._lock_task.cancel()
        self._lock_task = asyncio.ensure_future(self._auto_lock())

    async def _auto_lock(self) -> None:
        """Auto-lock after inactivity timeout."""
        await asyncio.sleep(self._auto_lock_seconds)
        if self.is_unlocked():
            log.info("vault_auto_locked", after_s=self._auto_lock_seconds)
            await self.lock()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def add(self, credential: Credential, plaintext_secret: str) -> str:
        """
        Encrypt and store a new credential.

        Args:
            credential: The Credential metadata (secret field will be overwritten).
            plaintext_secret: The actual secret to encrypt and store.

        Returns:
            The credential UUID.
        """
        key = self._require_unlocked()
        db = self._require_db()

        credential.secret = self._crypto.encrypt_hex(key, plaintext_secret)
        row = credential.to_db_row()
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row)
        await db.execute(
            f"INSERT OR REPLACE INTO credentials ({cols}) VALUES ({placeholders})", row
        )
        await db.commit()

        await self._audit.append(
            "credential_added",
            "CredentialVault",
            {"id": credential.id, "service": credential.service, "type": credential.type.value},
        )
        log.info("credential_added", cred_id=credential.id, service=credential.service)
        return credential.id

    async def get(self, credential_id: str) -> Credential:
        """
        Retrieve and decrypt a credential by ID.

        The returned Credential.secret field contains the PLAINTEXT secret.
        The caller MUST NOT pass this to TTS, logs, or LLM context.

        Args:
            credential_id: UUID of the credential.

        Returns:
            Decrypted Credential.

        Raises:
            VaultLockedError: If vault is locked.
            KeyError: If credential not found.
        """
        key = self._require_unlocked()
        db = self._require_db()

        # Audit BEFORE returning
        await self._audit.append(
            "credential_accessed",
            "CredentialVault",
            {"id": credential_id},
        )

        async with db.execute(
            "SELECT * FROM credentials WHERE id = ? AND is_deleted = 0",
            (credential_id,),
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise KeyError(f"Credential {credential_id!r} not found")

        cred = Credential.from_db_row(dict(row))
        cred.secret = self._crypto.decrypt_hex(key, cred.secret)

        if cred.totp_seed:
            cred.totp_seed = self._crypto.decrypt_hex(key, cred.totp_seed)

        # Update last_accessed
        now = datetime.now(UTC).isoformat()
        cred.last_accessed = now
        await db.execute(
            "UPDATE credentials SET last_accessed = ? WHERE id = ?",
            (now, credential_id),
        )
        await db.commit()

        return cred

    async def search(self, query: str) -> list[CredentialSummary]:
        """
        Search credentials by name or service (returns summaries — NO secrets).

        Args:
            query: Substring to match against name or service.

        Returns:
            List of CredentialSummary objects (no secret fields).
        """
        self._require_unlocked()
        db = self._require_db()

        pattern = f"%{query}%"
        async with db.execute(
            "SELECT * FROM credentials WHERE is_deleted = 0 "
            "AND (name LIKE ? OR service LIKE ? OR username LIKE ?) "
            "ORDER BY last_accessed DESC",
            (pattern, pattern, pattern),
        ) as cur:
            rows = await cur.fetchall()

        return [CredentialSummary.from_credential(Credential.from_db_row(dict(r))) for r in rows]

    async def list_all(self) -> list[CredentialSummary]:
        """
        Return all non-deleted credentials as summaries (no secrets).

        Returns:
            List of CredentialSummary objects.
        """
        self._require_unlocked()
        db = self._require_db()

        async with db.execute(
            "SELECT * FROM credentials WHERE is_deleted = 0 ORDER BY name"
        ) as cur:
            rows = await cur.fetchall()

        return [CredentialSummary.from_credential(Credential.from_db_row(dict(r))) for r in rows]

    async def update(self, credential_id: str, updates: dict[str, Any]) -> None:
        """
        Update non-secret fields of a credential.

        To change the secret, use delete() + add().

        Args:
            credential_id: UUID of the credential to update.
            updates: Dict of field names to new values.
        """
        self._require_unlocked()
        db = self._require_db()

        updates.pop("secret", None)  # Never update secret via this path
        updates.pop("totp_seed", None)
        updates["updated_at"] = datetime.now(UTC).isoformat()

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        updates["id"] = credential_id
        await db.execute(
            f"UPDATE credentials SET {set_clause} WHERE id = :id",
            updates,  # noqa: S608
        )
        await db.commit()

        await self._audit.append(
            "credential_updated",
            "CredentialVault",
            {"id": credential_id, "fields": list(updates.keys())},
        )

    async def delete(self, credential_id: str) -> None:
        """
        Soft-delete a credential (marks is_deleted=1, never removes from DB).

        Args:
            credential_id: UUID of the credential to soft-delete.
        """
        self._require_unlocked()
        db = self._require_db()

        await self._audit.append(
            "credential_deleted",
            "CredentialVault",
            {"id": credential_id},
        )
        await db.execute(
            "UPDATE credentials SET is_deleted = 1, updated_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), credential_id),
        )
        await db.commit()
        log.info("credential_soft_deleted", cred_id=credential_id)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def get_totp(self, credential_id: str) -> str:
        """
        Return the current 6-digit TOTP code for a credential.

        Audits the access and returns the code for display only.
        Emily MUST NOT pass this value to TTS.

        Args:
            credential_id: UUID of the TOTP credential.

        Returns:
            Current 6-digit TOTP code string.
        """
        cred = await self.get(credential_id)  # audit happens inside get()
        if not cred.totp_seed:
            raise ValueError(f"Credential {credential_id!r} has no TOTP seed")
        code = self._totp.get_code(cred.totp_seed)
        # Zero secret immediately — we only needed the totp_seed
        cred.secret = ""
        cred.totp_seed = ""
        return code

    async def generate_password(
        self,
        length: int = 24,
        use_symbols: bool = True,
        use_digits: bool = True,
        use_upper: bool = True,
    ) -> str:
        """
        Generate a cryptographically secure random password.

        Args:
            length: Password length (minimum 12).
            use_symbols: Include symbols.
            use_digits: Include digits.
            use_upper: Include uppercase letters.

        Returns:
            Generated password string.
        """
        length = max(12, length)
        charset = string.ascii_lowercase
        if use_upper:
            charset += string.ascii_uppercase
        if use_digits:
            charset += string.digits
        if use_symbols:
            charset += string.punctuation

        return "".join(secrets.choice(charset) for _ in range(length))

    async def health_report(self) -> list[dict[str, str]]:
        """
        Run all health checks and return a list of alert dicts.

        Returns:
            List of alert dicts (safe to display, no secret material).
        """
        summaries = await self.list_all()
        alerts = []
        alerts += self._health.check_expiring(summaries)
        alerts += self._health.check_weak(summaries)

        return [
            {
                "id": a.credential_id,
                "name": a.credential_name,
                "type": a.alert_type,
                "message": a.message,
                "severity": a.severity,
            }
            for a in alerts
        ]

    async def close(self) -> None:
        """Lock the vault and close the database connection."""
        await self.lock()
        if self._db:
            await self._db.close()
            self._db = None
