"""
Credential data models for the encrypted vault.

The `secret` field is NEVER stored in plaintext — it is always the
AES-GCM ciphertext blob from VaultCrypto. The VaultCrypto class handles
encryption/decryption so that plaintext bytes never leak beyond the
CredentialVault.get() call boundary.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class CredentialType(StrEnum):
    """Supported credential types."""

    PASSWORD = "PASSWORD"
    API_KEY = "API_KEY"
    SSH_KEY = "SSH_KEY"
    PIN = "PIN"
    WIFI = "WIFI"
    SEED_PHRASE = "SEED_PHRASE"
    TOTP = "TOTP"
    OTHER = "OTHER"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


@dataclass
class Credential:
    """
    A single credential entry.

    The `secret` and `totp_seed` fields contain AES-GCM ciphertext blobs
    (hex-encoded) when read from / written to the vault database. They are
    NEVER stored or transmitted as plaintext.
    """

    id: str = field(default_factory=_uuid)
    type: CredentialType = CredentialType.PASSWORD
    name: str = ""
    service: str = ""
    username: str = ""
    secret: str = ""  # AES-GCM ciphertext (hex) — NEVER plaintext at rest
    totp_seed: str = ""  # AES-GCM ciphertext (hex) — only for TOTP type
    url: str = ""
    tags: list[str] = field(default_factory=list)
    associated_entity_ids: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    last_accessed: str = field(default_factory=_now_iso)
    password_strength: float = 0.0
    expiry_date: str | None = None

    def to_db_row(self) -> dict[str, Any]:
        """Serialize to SQLite-compatible dict."""
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "service": self.service,
            "username": self.username,
            "secret": self.secret,
            "totp_seed": self.totp_seed,
            "url": self.url,
            "tags": json.dumps(self.tags),
            "associated_entity_ids": json.dumps(self.associated_entity_ids),
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed": self.last_accessed,
            "password_strength": self.password_strength,
            "expiry_date": self.expiry_date,
        }

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> Credential:
        """Deserialize from SQLite row dict."""
        return cls(
            id=row["id"],
            type=CredentialType(row["type"]),
            name=row["name"],
            service=row["service"],
            username=row["username"],
            secret=row["secret"],
            totp_seed=row.get("totp_seed", ""),
            url=row.get("url", ""),
            tags=json.loads(row.get("tags", "[]")),
            associated_entity_ids=json.loads(row.get("associated_entity_ids", "[]")),
            notes=row.get("notes", ""),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_accessed=row.get("last_accessed", row["created_at"]),
            password_strength=row.get("password_strength", 0.0),
            expiry_date=row.get("expiry_date"),
        )


@dataclass
class CredentialSummary:
    """
    Safe summary of a credential — contains NO secret material.

    Returned by vault.search() and vault.list() so the caller never
    sees plaintext secrets unless they explicitly call vault.get().
    """

    id: str
    type: CredentialType
    name: str
    service: str
    username: str
    url: str
    tags: list[str]
    created_at: str
    updated_at: str
    last_accessed: str
    password_strength: float
    expiry_date: str | None
    associated_entity_ids: list[str]

    @classmethod
    def from_credential(cls, cred: Credential) -> CredentialSummary:
        """Build a summary from a full Credential, stripping secret fields."""
        return cls(
            id=cred.id,
            type=cred.type,
            name=cred.name,
            service=cred.service,
            username=cred.username,
            url=cred.url,
            tags=cred.tags,
            created_at=cred.created_at,
            updated_at=cred.updated_at,
            last_accessed=cred.last_accessed,
            password_strength=cred.password_strength,
            expiry_date=cred.expiry_date,
            associated_entity_ids=cred.associated_entity_ids,
        )
