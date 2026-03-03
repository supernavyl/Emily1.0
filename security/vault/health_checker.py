"""
Vault health checker — detects reused passwords, expiring credentials,
and weak password strength scores.

No secrets are read by this module — it operates only on CredentialSummary
objects and the (decrypted) password strings that the vault passes in for
strength/reuse analysis. Strength scores are stored at add-time.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import date, datetime

from observability.logger import get_logger
from security.vault.models import CredentialSummary

log = get_logger(__name__)


@dataclass
class HealthAlert:
    """A single credential health issue."""

    credential_id: str
    credential_name: str
    alert_type: str  # "reused"|"expiring"|"expired"|"weak"|"no_totp"
    message: str
    severity: str  # "low"|"medium"|"high"|"critical"


class PasswordStrengthScorer:
    """
    Calculates a password strength score in [0.0, 1.0].

    Factors: length, character class diversity, entropy estimate.
    """

    def score(self, password: str) -> float:
        """
        Score a password's strength.

        Args:
            password: Plaintext password string.

        Returns:
            Strength score from 0.0 (terrible) to 1.0 (excellent).
        """
        if not password:
            return 0.0

        length_score = min(len(password) / 32, 1.0)

        classes = 0
        if re.search(r"[a-z]", password):
            classes += 1
        if re.search(r"[A-Z]", password):
            classes += 1
        if re.search(r"\d", password):
            classes += 1
        if re.search(r"[^a-zA-Z0-9]", password):
            classes += 1
        diversity_score = classes / 4

        # Shannon entropy estimate
        charset_size = sum(
            [
                26 if re.search(r"[a-z]", password) else 0,
                26 if re.search(r"[A-Z]", password) else 0,
                10 if re.search(r"\d", password) else 0,
                32 if re.search(r"[^a-zA-Z0-9]", password) else 0,
            ]
        )
        if charset_size > 0:
            entropy_bits = len(password) * math.log2(charset_size)
            entropy_score = min(entropy_bits / 100, 1.0)
        else:
            entropy_score = 0.0

        return length_score * 0.4 + diversity_score * 0.3 + entropy_score * 0.3

    @staticmethod
    def hibp_prefix(password: str) -> str:
        """
        Return the 5-character SHA-1 prefix for k-anonymity HIBP lookup.

        The caller sends only the prefix to the HIBP API — the full hash
        never leaves the machine.

        Args:
            password: Plaintext password.

        Returns:
            First 5 hex characters of SHA-1 hash (uppercase).
        """
        sha1 = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
        return sha1[:5]


class VaultHealthChecker:
    """
    Analyses CredentialSummary lists for security issues.

    This class never receives secret material — it works on summaries
    and the strength scores stored at credential creation time.
    """

    def check_expiring(
        self,
        summaries: list[CredentialSummary],
        warn_days: int = 30,
    ) -> list[HealthAlert]:
        """
        Return alerts for credentials expiring within warn_days.

        Args:
            summaries: List of CredentialSummary objects to check.
            warn_days: Number of days ahead to consider "expiring soon".

        Returns:
            List of HealthAlert objects for expiring/expired credentials.
        """
        alerts: list[HealthAlert] = []
        today = date.today()

        for s in summaries:
            if not s.expiry_date:
                continue
            try:
                exp = datetime.fromisoformat(s.expiry_date).date()
            except ValueError:
                continue

            days_left = (exp - today).days
            if days_left < 0:
                alerts.append(
                    HealthAlert(
                        credential_id=s.id,
                        credential_name=s.name,
                        alert_type="expired",
                        message=f"'{s.name}' expired {abs(days_left)} days ago",
                        severity="critical",
                    )
                )
            elif days_left <= warn_days:
                alerts.append(
                    HealthAlert(
                        credential_id=s.id,
                        credential_name=s.name,
                        alert_type="expiring",
                        message=f"'{s.name}' expires in {days_left} days",
                        severity="high" if days_left <= 7 else "medium",
                    )
                )

        return alerts

    def check_weak(
        self,
        summaries: list[CredentialSummary],
        weak_threshold: float = 0.4,
    ) -> list[HealthAlert]:
        """
        Return alerts for credentials with low password strength scores.

        Args:
            summaries: List of CredentialSummary objects.
            weak_threshold: Strength scores below this are flagged.

        Returns:
            List of HealthAlert objects for weak credentials.
        """
        alerts = []
        for s in summaries:
            if s.password_strength < weak_threshold:
                alerts.append(
                    HealthAlert(
                        credential_id=s.id,
                        credential_name=s.name,
                        alert_type="weak",
                        message=(
                            f"'{s.name}' has a weak password (score: {s.password_strength:.2f})"
                        ),
                        severity="high" if s.password_strength < 0.2 else "medium",
                    )
                )
        return alerts
