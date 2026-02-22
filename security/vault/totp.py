"""
TOTP (Time-based One-Time Password) generation for vault credentials.

Uses pyotp to generate RFC 6238-compliant 6-digit codes.
The TOTP seed is stored encrypted in the vault — it is decrypted in memory,
used to generate the current code, then the plaintext seed is discarded.

Emily never speaks TOTP codes via TTS. All TOTP output is display-only.
"""

from __future__ import annotations

import time

import pyotp

from observability.logger import get_logger

log = get_logger(__name__)


class TOTPProvider:
    """
    Stateless TOTP code generator.

    Accepts the plaintext base32-encoded TOTP seed (decrypted from vault)
    and returns the current 6-digit code. The seed is not retained beyond
    the method call.
    """

    def get_code(self, plaintext_seed: str) -> str:
        """
        Return the current 6-digit TOTP code for the given seed.

        Args:
            plaintext_seed: Base32-encoded TOTP secret (e.g., from Google Authenticator).

        Returns:
            Current 6-digit TOTP code as a string.

        Raises:
            ValueError: If the seed is not valid base32.
        """
        try:
            totp = pyotp.TOTP(plaintext_seed.strip().upper())
            code = totp.now()
            log.debug("totp_code_generated")
            return code
        except Exception as exc:
            raise ValueError(f"Invalid TOTP seed: {exc}") from exc

    def get_remaining_seconds(self, plaintext_seed: str) -> int:
        """
        Return seconds remaining until the current TOTP code expires.

        Args:
            plaintext_seed: Base32-encoded TOTP secret.

        Returns:
            Seconds remaining in the current 30-second TOTP window.
        """
        totp = pyotp.TOTP(plaintext_seed.strip().upper())
        return totp.interval - int(time.time()) % totp.interval

    def verify(self, plaintext_seed: str, code: str, valid_window: int = 1) -> bool:
        """
        Verify a TOTP code allowing for clock drift.

        Args:
            plaintext_seed: Base32-encoded TOTP secret.
            code: The 6-digit code to verify.
            valid_window: Number of 30-second windows to allow before/after current.

        Returns:
            True if the code is valid within the allowed window.
        """
        totp = pyotp.TOTP(plaintext_seed.strip().upper())
        return totp.verify(code, valid_window=valid_window)
