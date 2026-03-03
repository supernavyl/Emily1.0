"""
Owner Identity System — Single user ownership and privacy protection.

Emily has ONE owner who she trusts completely. All other speakers are treated
as guests with limited access. Personal information is NEVER shared with non-owners.

Features:
- Voice enrollment for owner recognition
- Passphrase verification as backup
- Privacy-aware response filtering
- Guest mode with restricted information access
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


class SpeakerType(Enum):
    """Who Emily thinks is speaking."""

    OWNER = auto()  # The one true owner - full trust
    GUEST = auto()  # Someone else - limited access
    UNKNOWN = auto()  # Can't determine - treat as guest
    VERIFICATION_NEEDED = auto()  # Need to verify identity


@dataclass
class SpeakerIdentity:
    """Current speaker identification state."""

    speaker_type: SpeakerType = SpeakerType.UNKNOWN
    confidence: float = 0.0
    last_verified: float = 0.0
    session_start: float = field(default_factory=time.time)
    failed_attempts: int = 0


@dataclass
class OwnerProfile:
    """The owner's identity and verification data."""

    name: str = ""
    passphrase_hash: str = ""  # SHA-256 hash of passphrase
    voice_enrolled: bool = False
    voice_embedding: list[float] | None = None
    created_at: float = field(default_factory=time.time)
    last_verified: float = 0.0
    verification_count: int = 0

    # Custom name the owner chose for their AI (defaults to "Emily")
    ai_name: str = "Emily"

    # Email for password reset
    email: str = ""

    # Preferred TTS voice (Edge TTS voice ID, e.g. "en-US-JennyNeural")
    voice_preference: str = ""

    # Personal data the owner has shared
    personal_facts: dict[str, Any] = field(default_factory=dict)
    private_preferences: dict[str, Any] = field(default_factory=dict)
    sensitive_topics: list[str] = field(default_factory=list)


# Topics Emily should NEVER discuss with guests
_PRIVATE_TOPICS = [
    "schedule",
    "calendar",
    "appointments",
    "location",
    "address",
    "where I live",
    "passwords",
    "credentials",
    "secrets",
    "health",
    "medical",
    "doctor",
    "finances",
    "money",
    "bank",
    "salary",
    "relationships",
    "family",
    "friends",
    "work",
    "job",
    "employer",
    "colleagues",
    "personal projects",
    "private",
    "conversations",
    "what we talked about",
    "my data",
    "my information",
]

# Phrases that might be fishing for personal info
_SUSPICIOUS_PHRASES = [
    "tell me about",
    "what do you know about",
    "what has",
    "what did",
    "where does",
    "what's their",
    "share",
    "reveal",
    "password",
    "secret",
]


class OwnerIdentityManager:
    """
    Manages owner identity verification and privacy protection.

    Emily has exactly ONE owner. When she first starts, she asks who the owner is
    and sets up verification. All future interactions check if the speaker is
    the owner before sharing any personal information.
    """

    _VERIFICATION_TIMEOUT_S = 3600  # Re-verify after 1 hour of inactivity
    _MAX_FAILED_ATTEMPTS = 3
    _LOCKOUT_DURATION_S = 300  # 5 minute lockout after failed attempts

    def __init__(self, data_path: str = "data/owner_identity.json") -> None:
        self._path = Path(data_path)
        self._owner: OwnerProfile | None = None
        self._current_speaker = SpeakerIdentity()
        self._lockout_until: float = 0.0

    async def load(self) -> None:
        """Load owner identity from disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)

        if self._path.exists():
            try:
                raw = self._path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._owner = OwnerProfile(**data)
                log.info("owner_identity_loaded", owner_name=self._owner.name)
            except Exception as exc:
                log.warning("owner_identity_load_failed", error=str(exc))
                self._owner = None
        else:
            self._owner = None
            log.info("no_owner_configured")

    async def save(self) -> None:
        """Persist owner identity to disk."""
        if self._owner is None:
            return

        data = {
            "name": self._owner.name,
            "ai_name": self._owner.ai_name,
            "email": self._owner.email,
            "voice_preference": self._owner.voice_preference,
            "passphrase_hash": self._owner.passphrase_hash,
            "voice_enrolled": self._owner.voice_enrolled,
            "voice_embedding": self._owner.voice_embedding,
            "created_at": self._owner.created_at,
            "last_verified": self._owner.last_verified,
            "verification_count": self._owner.verification_count,
            "personal_facts": self._owner.personal_facts,
            "private_preferences": self._owner.private_preferences,
            "sensitive_topics": self._owner.sensitive_topics,
        }

        self._path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("owner_identity_saved")

    @property
    def has_owner(self) -> bool:
        """True if an owner has been registered."""
        return self._owner is not None and bool(self._owner.name)

    @property
    def owner_name(self) -> str:
        """The owner's name, or empty string if no owner."""
        return self._owner.name if self._owner else ""

    @property
    def ai_name(self) -> str:
        """The custom name the owner chose for this AI."""
        return self._owner.ai_name if self._owner else "Emily"

    async def update_ai_name(self, name: str) -> None:
        """Update the AI's display name and persist to disk."""
        if self._owner:
            self._owner.ai_name = name.strip() or "Emily"
            await self.save()
            log.info("ai_name_updated", ai_name=self._owner.ai_name)

    async def reset_passphrase(self, current: str, new: str) -> bool:
        """Verify current passphrase then set a new one."""
        if not self.has_owner:
            return False
        current_hash = hashlib.sha256(current.encode()).hexdigest()
        if current_hash != self._owner.passphrase_hash:
            log.warning("passphrase_reset_wrong_current")
            return False
        self._owner.passphrase_hash = hashlib.sha256(new.encode()).hexdigest()
        await self.save()
        log.info("passphrase_reset_success")
        return True

    @property
    def is_owner_verified(self) -> bool:
        """True if current speaker is verified as the owner."""
        if self._current_speaker.speaker_type != SpeakerType.OWNER:
            return False
        # Check if verification has expired
        elapsed = time.time() - self._current_speaker.last_verified
        if elapsed > self._VERIFICATION_TIMEOUT_S:
            self._current_speaker.speaker_type = SpeakerType.VERIFICATION_NEEDED
            return False
        return True

    @property
    def current_speaker_type(self) -> SpeakerType:
        """Get the current speaker classification."""
        return self._current_speaker.speaker_type

    def is_locked_out(self) -> bool:
        """Check if system is in lockout due to failed attempts."""
        return time.time() < self._lockout_until

    async def register_owner(
        self,
        name: str,
        passphrase: str,
        personal_facts: dict[str, Any] | None = None,
    ) -> bool:
        """
        Register the one and only owner.

        Args:
            name: Owner's name.
            passphrase: Secret passphrase for verification.
            personal_facts: Initial personal facts to store.

        Returns:
            True if registration succeeded.
        """
        if self.has_owner:
            log.warning("owner_already_registered", existing=self._owner.name)
            return False

        # Hash the passphrase
        passphrase_hash = hashlib.sha256(passphrase.encode()).hexdigest()

        self._owner = OwnerProfile(
            name=name,
            passphrase_hash=passphrase_hash,
            personal_facts=personal_facts or {},
        )

        # Auto-verify after registration
        self._current_speaker = SpeakerIdentity(
            speaker_type=SpeakerType.OWNER,
            confidence=1.0,
            last_verified=time.time(),
        )
        self._owner.last_verified = time.time()
        self._owner.verification_count = 1

        await self.save()
        log.info("owner_registered", name=name)
        return True

    async def verify_passphrase(self, passphrase: str) -> bool:
        """
        Verify identity using passphrase.

        Args:
            passphrase: The passphrase to check.

        Returns:
            True if passphrase matches and speaker is now verified as owner.
        """
        if not self.has_owner:
            return False

        if self.is_locked_out():
            log.warning("verification_locked_out")
            return False

        passphrase_hash = hashlib.sha256(passphrase.encode()).hexdigest()

        if passphrase_hash == self._owner.passphrase_hash:
            # Verified!
            self._current_speaker = SpeakerIdentity(
                speaker_type=SpeakerType.OWNER,
                confidence=1.0,
                last_verified=time.time(),
            )
            self._owner.last_verified = time.time()
            self._owner.verification_count += 1
            await self.save()
            log.info("owner_verified_by_passphrase")
            return True
        else:
            # Failed attempt
            self._current_speaker.failed_attempts += 1
            if self._current_speaker.failed_attempts >= self._MAX_FAILED_ATTEMPTS:
                self._lockout_until = time.time() + self._LOCKOUT_DURATION_S
                log.warning("verification_lockout_triggered")
            log.warning("passphrase_verification_failed")
            return False

    def mark_as_guest(self) -> None:
        """Mark the current speaker as a guest (not the owner)."""
        self._current_speaker = SpeakerIdentity(
            speaker_type=SpeakerType.GUEST,
            confidence=0.8,
            last_verified=time.time(),
        )
        log.info("speaker_marked_as_guest")

    def require_verification(self) -> None:
        """Require re-verification before continuing."""
        self._current_speaker.speaker_type = SpeakerType.VERIFICATION_NEEDED
        log.info("verification_required")

    # --- Privacy Protection ---

    def is_private_query(self, text: str) -> bool:
        """
        Check if a query is asking for private/personal information.

        Args:
            text: The user's query.

        Returns:
            True if this appears to be asking for personal info.
        """
        text_lower = text.lower()

        # Check for private topics
        for topic in _PRIVATE_TOPICS:
            if topic in text_lower:
                return True

        # Check if asking about the owner
        if self._owner and self._owner.name:
            owner_name_lower = self._owner.name.lower()
            # Asking about owner by name
            if owner_name_lower in text_lower and any(
                phrase in text_lower for phrase in _SUSPICIOUS_PHRASES
            ):
                return True

        return False

    def filter_response_for_guest(self, response: str) -> str:
        """
        Filter Emily's response to remove personal information for guests.

        Args:
            response: Emily's original response.

        Returns:
            Filtered response safe for guests.
        """
        if self.is_owner_verified:
            return response  # Owner gets full response

        # For guests, we need to check if response contains personal info
        # This is a simple implementation - could be enhanced with LLM

        filtered = response

        # Remove owner's name from responses to guests
        if self._owner and self._owner.name:
            # Don't reveal the owner's name to guests
            filtered = filtered.replace(self._owner.name, "my owner")

        # Remove any mentioned personal facts
        if self._owner:
            for fact_value in self._owner.personal_facts.values():
                if isinstance(fact_value, str) and len(fact_value) > 2:
                    filtered = filtered.replace(str(fact_value), "[private]")

        return filtered

    def get_privacy_aware_system_prompt_addition(self) -> str:
        """
        Get additional system prompt text for privacy awareness.

        Returns:
            System prompt addition based on current speaker.
        """
        if not self.has_owner:
            return ""

        if self.is_owner_verified:
            return f"""
SPEAKER STATUS: You are talking to your owner, {self._owner.name}.
You can freely discuss personal information, private topics, and share everything you know.
Treat them with familiarity and trust.
"""

        if self._current_speaker.speaker_type == SpeakerType.GUEST:
            return f"""
SPEAKER STATUS: You are talking to a GUEST (not your owner {self._owner.name}).
CRITICAL PRIVACY RULES:
- NEVER share personal information about your owner
- NEVER discuss private conversations, schedules, locations, or personal facts
- NEVER reveal your owner's name or details about them
- If asked about personal topics, politely decline: "I can only discuss that with my owner."
- You can have normal conversations about general topics
- Be friendly but protect your owner's privacy absolutely
"""

        if self._current_speaker.speaker_type == SpeakerType.VERIFICATION_NEEDED:
            return """
SPEAKER STATUS: Identity verification required.
Ask the speaker to verify their identity with their passphrase before discussing any personal topics.
You can only discuss general, non-personal topics until verification.
"""

        return """
SPEAKER STATUS: Unknown speaker.
Treat as a guest. Do not share any personal information until identity is verified.
"""

    # --- Personal Data Management ---

    async def add_personal_fact(self, key: str, value: Any) -> None:
        """Store a personal fact about the owner (only owner can add)."""
        if not self.is_owner_verified:
            log.warning("unauthorized_personal_fact_add_attempt")
            return

        if self._owner:
            self._owner.personal_facts[key] = value
            await self.save()

    def get_personal_fact(self, key: str) -> Any | None:
        """Get a personal fact (only returns if owner is verified)."""
        if not self.is_owner_verified:
            return None
        return self._owner.personal_facts.get(key) if self._owner else None

    async def add_sensitive_topic(self, topic: str) -> None:
        """Mark a topic as sensitive (never discuss with guests)."""
        if not self.is_owner_verified:
            return
        if self._owner and topic not in self._owner.sensitive_topics:
            self._owner.sensitive_topics.append(topic)
            await self.save()

    def get_guest_safe_profile(self) -> dict[str, Any]:
        """Get a minimal profile safe to use in guest conversations."""
        return {
            "has_owner": self.has_owner,
            "speaker_type": self._current_speaker.speaker_type.name,
            # No personal details!
        }

    def get_owner_full_profile(self) -> dict[str, Any] | None:
        """Get full owner profile (only if verified as owner)."""
        if not self.is_owner_verified or not self._owner:
            return None
        return {
            "name": self._owner.name,
            "personal_facts": self._owner.personal_facts,
            "private_preferences": self._owner.private_preferences,
            "sensitive_topics": self._owner.sensitive_topics,
        }
