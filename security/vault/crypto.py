"""
Vault cryptography: Argon2id KDF + AES-256-GCM per-credential encryption.

Security model:
- Master password is hashed with Argon2id to derive a 32-byte vault key.
- Each credential's secret is encrypted with AES-256-GCM using the vault key
  and a freshly generated 96-bit nonce.
- Ciphertext format: hex(nonce_12_bytes || ciphertext || tag_16_bytes)
- Master password is NEVER stored or written to disk in any form.
- Derived key bytes are zeroed in memory after use via ctypes memset.
- This module has no I/O — it only transforms bytes.
"""

from __future__ import annotations

import ctypes
import os
from typing import Final

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# Argon2id parameters (OWASP recommended minimums for interactive login)
_ARGON2_TIME_COST: Final = 3
_ARGON2_MEMORY_COST: Final = 65536   # 64 MiB
_ARGON2_PARALLELISM: Final = 4
_KEY_LEN: Final = 32                  # 256-bit AES key
_NONCE_LEN: Final = 12                # 96-bit GCM nonce

# Fixed salt for KDF — stored alongside vault metadata, not the master password.
# Using a fixed salt means the vault key is always re-derivable from the
# master password. For per-user entropy we include vault_id in the salt.
_SALT_PREFIX: Final = b"emily_vault_v1_"


class VaultCrypto:
    """
    Stateless cryptographic helpers for the CredentialVault.

    All methods accept/return bytes. The vault class is responsible for
    hex-encoding ciphertext for database storage.

    The derived key is held in a bytearray so _zero_bytes() can overwrite it.
    """

    def __init__(
        self,
        time_cost: int = _ARGON2_TIME_COST,
        memory_cost: int = _ARGON2_MEMORY_COST,
        parallelism: int = _ARGON2_PARALLELISM,
    ) -> None:
        """
        Args:
            time_cost: Argon2id iteration count.
            memory_cost: Argon2id memory in KiB.
            parallelism: Argon2id parallelism factor.
        """
        self._time_cost = time_cost
        self._memory_cost = memory_cost
        self._parallelism = parallelism

    def derive_key(self, master_password: str, vault_salt: bytes) -> bytearray:
        """
        Derive a 256-bit vault key from the master password using Argon2id.

        The returned bytearray should be zeroed with zero_key() after use.

        Args:
            master_password: The user's master password (plaintext, in memory only).
            vault_salt: Unique salt bytes for this vault instance.

        Returns:
            32-byte derived key as a bytearray.
        """
        raw = hash_secret_raw(
            secret=master_password.encode(),
            salt=vault_salt,
            time_cost=self._time_cost,
            memory_cost=self._memory_cost,
            parallelism=self._parallelism,
            hash_len=_KEY_LEN,
            type=Type.ID,
        )
        return bytearray(raw)

    @staticmethod
    def zero_key(key: bytearray) -> None:
        """
        Overwrite key bytes with zeros using ctypes to prevent compiler optimisation.

        Args:
            key: The key bytearray to zero.
        """
        if len(key) == 0:
            return
        addr = (ctypes.c_char * len(key)).from_buffer(key)
        ctypes.memset(addr, 0, len(key))

    @staticmethod
    def make_vault_salt(vault_id: str) -> bytes:
        """
        Build a deterministic salt from the vault UUID + a fixed prefix.

        The salt must be stored alongside the vault (not derived from the password)
        so the same key can always be rederived.

        Args:
            vault_id: Unique vault identifier (UUID string).

        Returns:
            Salt bytes (at least 16 bytes).
        """
        combined = _SALT_PREFIX + vault_id.encode()
        # Pad/truncate to exactly 32 bytes
        padded = (combined * 2)[:32]
        return padded

    def encrypt(self, key: bytearray, plaintext: bytes) -> bytes:
        """
        Encrypt plaintext with AES-256-GCM.

        Output format: nonce (12 bytes) || ciphertext+tag (variable).

        Args:
            key: 32-byte derived vault key.
            plaintext: Data to encrypt.

        Returns:
            nonce + ciphertext bytes.
        """
        nonce = os.urandom(_NONCE_LEN)
        aesgcm = AESGCM(bytes(key))
        ciphertext = aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, key: bytearray, blob: bytes) -> bytes:
        """
        Decrypt an AES-256-GCM blob.

        Args:
            key: 32-byte derived vault key.
            blob: nonce (12 bytes) + ciphertext from encrypt().

        Returns:
            Plaintext bytes.

        Raises:
            cryptography.exceptions.InvalidTag: If decryption fails (bad key or tampered data).
        """
        nonce = blob[:_NONCE_LEN]
        ciphertext = blob[_NONCE_LEN:]
        aesgcm = AESGCM(bytes(key))
        return aesgcm.decrypt(nonce, ciphertext, None)

    def encrypt_hex(self, key: bytearray, plaintext: str) -> str:
        """
        Encrypt a plaintext string and return hex-encoded ciphertext for DB storage.

        Args:
            key: Derived vault key.
            plaintext: Secret string (password, API key, etc.).

        Returns:
            Hex-encoded encrypted blob.
        """
        blob = self.encrypt(key, plaintext.encode())
        return blob.hex()

    def decrypt_hex(self, key: bytearray, hex_blob: str) -> str:
        """
        Decrypt a hex-encoded ciphertext blob back to a plaintext string.

        Args:
            key: Derived vault key.
            hex_blob: Hex-encoded blob from encrypt_hex().

        Returns:
            Plaintext secret string.
        """
        blob = bytes.fromhex(hex_blob)
        return self.decrypt(key, blob).decode()
