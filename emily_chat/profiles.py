"""Emily system profiles: named role-to-model mappings.

Profiles let users build "Emily systems" (e.g. Coding Emily, Research Emily)
by assigning a model to each role. Roles align with skills where applicable.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

# Role keys used in profiles. Map to skills: core=default, coding=code, etc.
EMILY_PROFILE_ROLES: list[tuple[str, str]] = [
    ("core", "Core (default)"),
    ("coding", "Coding"),
    ("research", "Research"),
    ("writing", "Writing"),
    ("reasoning", "Reasoning"),
    ("fast", "Fast"),
]

# Skill ID -> profile role key (for resolving model from profile by current skill)
SKILL_TO_ROLE: dict[str, str] = {
    "normal": "core",
    "code": "coding",
    "research": "research",
    "writing": "writing",
    "deep_think": "reasoning",
    "translate": "core",
    "concise": "fast",
}


class EmilyProfile(BaseModel):
    """A named system profile mapping roles to registry model keys."""

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    roles: dict[str, str] = Field(default_factory=dict)

    def get_model_for_role(self, role: str, fallback: str = "auto") -> str:
        """Return the registry key for *role*, or *fallback* if unset."""
        return self.roles.get(role, fallback)


_PROFILES_DIR = Path.home() / ".emily-chat"
_PROFILES_FILE = _PROFILES_DIR / "profiles.json"

_DEFAULT_PROFILE_ID = "default"


def _default_profile() -> EmilyProfile:
    """Built-in default profile (all roles auto)."""
    return EmilyProfile(
        id=_DEFAULT_PROFILE_ID,
        name="Default",
        roles={role: "auto" for role, _ in EMILY_PROFILE_ROLES},
    )


def load_profiles() -> list[EmilyProfile]:
    """Load all profiles from disk. Ensures at least the default profile exists."""
    if not _PROFILES_FILE.exists():
        return [_default_profile()]
    try:
        raw = json.loads(_PROFILES_FILE.read_text(encoding="utf-8"))
        profiles = [EmilyProfile.model_validate(p) for p in raw.get("profiles", [])]
        if not any(p.id == _DEFAULT_PROFILE_ID for p in profiles):
            profiles.insert(0, _default_profile())
        return profiles
    except (json.JSONDecodeError, ValueError):
        return [_default_profile()]


def save_profiles(profiles: list[EmilyProfile]) -> None:
    """Persist profiles to disk."""
    _PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    data = {"profiles": [p.model_dump() for p in profiles]}
    _PROFILES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_profile(profiles: list[EmilyProfile], profile_id: str) -> EmilyProfile | None:
    """Return the profile with *profile_id*, or None."""
    for p in profiles:
        if p.id == profile_id:
            return p
    return None


def resolve_model_for_skill(
    profiles: list[EmilyProfile],
    active_profile_id: str,
    skill_id: str,
    fallback_model: str = "auto",
) -> str:
    """Resolve the registry model key for the current skill and active profile.

    Args:
        profiles: All loaded profiles.
        active_profile_id: Currently active profile id.
        skill_id: Current skill (e.g. code, research, normal).
        fallback_model: If profile not found or role unset, use this.

    Returns:
        Registry key (e.g. codestral-2, auto, ollama-local).
    """
    profile = get_profile(profiles, active_profile_id)
    if profile is None:
        return fallback_model
    role = SKILL_TO_ROLE.get(skill_id, "core")
    return profile.get_model_for_role(role, fallback=fallback_model)
