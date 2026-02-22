"""
Encryption at rest using `age` (https://age-encryption.org/).

All sensitive data files (episodic memory DB, procedural JSON,
knowledge graph, etc.) are encrypted with a native-age identity key
stored in the user's home directory. The key is never written to disk
in plaintext after initial generation.

Uses pyrage (Python bindings for the Rust age library) when available,
falling back to the `age` CLI tool.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

from observability.logger import get_logger

log = get_logger(__name__)

_DEFAULT_KEY_PATH = Path.home() / ".emily_key"


def _pyrage_available() -> bool:
    try:
        import pyrage  # type: ignore[import-untyped]  # noqa: F401
        return True
    except ImportError:
        return False


def _age_cli_available() -> bool:
    try:
        subprocess.run(["age", "--version"], check=True, capture_output=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


class AgeEncryption:
    """
    age-based file encryption / decryption.

    Generates a native-age identity key on first use.
    Encrypts/decrypts bytes in memory using pyrage or age CLI.
    When strict=True (e.g. encrypt_at_rest is true), no plaintext fallback;
    missing backend or key raises RuntimeError.
    """

    def __init__(
        self,
        key_path: Path = _DEFAULT_KEY_PATH,
        strict: bool = False,
    ) -> None:
        """
        Args:
            key_path: Path to the age identity key file (~/.emily_key).
            strict: If True, do not fall back to plaintext; raise when unavailable.
        """
        self._key_path = key_path
        self._strict = strict
        self._pyrage = _pyrage_available()
        self._age_cli = _age_cli_available()
        if not self._pyrage and not self._age_cli:
            if strict:
                raise RuntimeError(
                    "Encryption required but no backend available. "
                    "Install pyrage (pip install pyrage) or age CLI."
                )
            log.warning("age_encryption_unavailable_using_plaintext")

    def is_available(self) -> bool:
        """Return True if any encryption backend is available."""
        return self._pyrage or self._age_cli

    def ensure_key(self) -> Path:
        """
        Ensure an age identity key exists. Generate one if not.

        Returns:
            Path to the key file.
        """
        if self._key_path.exists():
            return self._key_path

        if self._pyrage:
            import pyrage
            identity = pyrage.x25519.Identity.generate()
            self._key_path.write_text(str(identity))
            self._key_path.chmod(0o600)
            log.info("age_key_generated", path=str(self._key_path))
            return self._key_path

        if self._age_cli:
            result = subprocess.run(
                ["age-keygen", "-o", str(self._key_path)],
                check=True, capture_output=True,
            )
            self._key_path.chmod(0o600)
            log.info("age_key_generated_cli", path=str(self._key_path))
            return self._key_path

        raise RuntimeError("Cannot generate age key: neither pyrage nor age-keygen is available.")

    def encrypt_bytes(self, plaintext: bytes) -> bytes:
        """
        Encrypt bytes with the identity key.

        Args:
            plaintext: Raw bytes to encrypt.

        Returns:
            Encrypted bytes.

        Raises:
            RuntimeError: When strict and encryption backend is unavailable.
        """
        if not self.is_available():
            if self._strict:
                raise RuntimeError(
                    "Encryption required but no backend available. "
                    "Install pyrage or age CLI."
                )
            return plaintext

        self.ensure_key()

        if self._pyrage:
            import pyrage
            identity_str = self._key_path.read_text().strip()
            identity = pyrage.x25519.Identity.from_str(identity_str)
            recipient = identity.to_public()
            return pyrage.encrypt(plaintext, [recipient])

        # CLI fallback: pipe through stdin/stdout
        result = subprocess.run(
            ["age", "--encrypt", "--identity", str(self._key_path)],
            input=plaintext,
            capture_output=True,
            check=True,
        )
        return result.stdout

    def decrypt_bytes(self, ciphertext: bytes) -> bytes:
        """
        Decrypt bytes with the identity key.

        Args:
            ciphertext: Encrypted bytes.

        Returns:
            Plaintext bytes.

        Raises:
            RuntimeError: When strict and encryption backend is unavailable.
        """
        if not self.is_available():
            if self._strict:
                raise RuntimeError(
                    "Encryption required but no backend available. "
                    "Install pyrage or age CLI."
                )
            return ciphertext

        if self._pyrage:
            import pyrage
            identity_str = self._key_path.read_text().strip()
            identity = pyrage.x25519.Identity.from_str(identity_str)
            return pyrage.decrypt(ciphertext, [identity])

        result = subprocess.run(
            ["age", "--decrypt", "--identity", str(self._key_path)],
            input=ciphertext,
            capture_output=True,
            check=True,
        )
        return result.stdout

    def encrypt_file(self, path: Path) -> None:
        """
        Encrypt a file in place (overwrites with ciphertext).

        Args:
            path: Path to the file to encrypt.
        """
        plaintext = path.read_bytes()
        encrypted = self.encrypt_bytes(plaintext)
        path.write_bytes(encrypted)
        log.debug("file_encrypted", path=str(path))

    def decrypt_file(self, path: Path) -> None:
        """
        Decrypt a file in place (overwrites with plaintext).

        Args:
            path: Path to the encrypted file.
        """
        ciphertext = path.read_bytes()
        plaintext = self.decrypt_bytes(ciphertext)
        path.write_bytes(plaintext)
        log.debug("file_decrypted", path=str(path))

    async def ensure_key_async(self) -> Path:
        """Async wrapper for ensure_key (avoids blocking subprocess calls)."""
        return await asyncio.to_thread(self.ensure_key)

    async def encrypt_bytes_async(self, plaintext: bytes) -> bytes:
        """Async wrapper for encrypt_bytes."""
        return await asyncio.to_thread(self.encrypt_bytes, plaintext)

    async def decrypt_bytes_async(self, ciphertext: bytes) -> bytes:
        """Async wrapper for decrypt_bytes."""
        return await asyncio.to_thread(self.decrypt_bytes, ciphertext)

    async def encrypt_file_async(self, path: Path) -> None:
        """Async wrapper for encrypt_file."""
        await asyncio.to_thread(self.encrypt_file, path)

    async def decrypt_file_async(self, path: Path) -> None:
        """Async wrapper for decrypt_file."""
        await asyncio.to_thread(self.decrypt_file, path)
