"""
Privacy Filter — Protects personal information from non-owners.

This module intercepts Emily's responses and filters out personal
information when the speaker is not verified as the owner.
"""

from __future__ import annotations

import re
from typing import Any

from observability.logger import get_logger
from users.owner_identity import OwnerIdentityManager

log = get_logger(__name__)


# Phrases that indicate Emily is about to share personal info
_PERSONAL_INFO_PATTERNS = [
    r"your name is",
    r"you told me",
    r"you mentioned",
    r"you said",
    r"I remember you",
    r"you work",
    r"your job",
    r"you live",
    r"your address",
    r"your schedule",
    r"your appointment",
    r"your password",
    r"your email",
    r"your phone",
    r"your family",
    r"your wife|husband|partner",
    r"your children|kids",
    r"your health",
    r"your doctor",
    r"your bank",
    r"your salary",
    r"your income",
]

# Generic refusal messages for guests
_GUEST_REFUSALS = [
    "I'm sorry, but I can only discuss that with my owner.",
    "That's personal information I can't share.",
    "I need to keep that private. Is there something else I can help with?",
    "I'm not able to share personal details. What else can I help you with?",
]


class PrivacyFilter:
    """
    Filters Emily's responses based on speaker identity.

    When speaking to guests, removes or replaces personal information
    to protect the owner's privacy.
    """

    def __init__(self, identity_manager: OwnerIdentityManager) -> None:
        self._identity = identity_manager
        self._refusal_index = 0

    def should_filter(self) -> bool:
        """Check if filtering is needed (not owner)."""
        return not self._identity.is_owner_verified

    def filter_response(self, response: str) -> str:
        """
        Filter a response to remove personal information if needed.

        Args:
            response: Emily's original response.

        Returns:
            Filtered response safe for the current speaker.
        """
        if self._identity.is_owner_verified:
            return response  # Owner gets everything

        filtered = response

        # Check for personal info patterns
        for pattern in _PERSONAL_INFO_PATTERNS:
            if re.search(pattern, response, re.IGNORECASE):
                # Found personal info - return refusal
                return self._get_refusal()

        # Use the identity manager's filter
        filtered = self._identity.filter_response_for_guest(filtered)

        return filtered

    def _get_refusal(self) -> str:
        """Get a varied refusal message."""
        refusal = _GUEST_REFUSALS[self._refusal_index % len(_GUEST_REFUSALS)]
        self._refusal_index += 1
        return refusal

    def check_query_privacy(self, query: str) -> tuple[bool, str | None]:
        """
        Check if a query is asking for private information.

        Args:
            query: The user's query.

        Returns:
            Tuple of (is_private, refusal_message).
            If is_private is True and speaker is not owner, use the refusal.
        """
        if self._identity.is_owner_verified:
            return False, None  # Owner can ask anything

        if self._identity.is_private_query(query):
            return True, self._get_refusal()

        return False, None

    def get_system_prompt_addition(self) -> str:
        """Get privacy-aware system prompt addition."""
        return self._identity.get_privacy_aware_system_prompt_addition()


def create_privacy_aware_messages(
    identity_manager: OwnerIdentityManager,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Add privacy awareness to conversation messages.

    Args:
        identity_manager: OwnerIdentityManager instance.
        messages: Original conversation messages.

    Returns:
        Messages with privacy instructions injected.
    """
    privacy_addition = identity_manager.get_privacy_aware_system_prompt_addition()

    if not privacy_addition:
        return messages

    # Find system message and append privacy rules
    new_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            new_content = msg["content"] + "\n\n" + privacy_addition
            new_messages.append({"role": "system", "content": new_content})
        else:
            new_messages.append(msg)

    return new_messages
