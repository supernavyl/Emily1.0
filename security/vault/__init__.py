"""Encrypted credential vault for Emily — Argon2id KDF + AES-GCM per credential."""

from security.vault.vault import CredentialVault
from security.vault.crypto import VaultCrypto
from security.vault.models import Credential, CredentialType, CredentialSummary

__all__ = [
    "CredentialVault",
    "VaultCrypto",
    "Credential",
    "CredentialType",
    "CredentialSummary",
]
