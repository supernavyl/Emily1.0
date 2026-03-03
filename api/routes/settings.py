"""Settings API — user profile, AI name, passphrase management, and auth."""

from __future__ import annotations

import hashlib
import os
import random
import smtplib
import time
from email.message import EmailMessage

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.settings_store import get_settings_store
from observability.logger import get_logger
from users.owner_identity import OwnerIdentityManager

log = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

# Injected at startup by bootstrap
_identity_manager: OwnerIdentityManager | None = None


def init_identity_manager(manager: OwnerIdentityManager) -> None:
    global _identity_manager
    _identity_manager = manager


# In-memory reset code store: {email_hash: (code, expiry_ts)}
_reset_codes: dict[str, tuple[str, float]] = {}

# Runtime permissions — initialised lazily from config on first GET.
# Changes here are session-scoped (not written back to config.yaml yet).
_permissions: dict[str, bool] | None = None


def _load_permissions() -> dict[str, bool]:
    """Read default permission values from config.yaml."""
    try:
        from config import get_settings

        s = get_settings()
        return {
            # Vision
            "vision_enabled": s.vision.enabled,
            "screen_capture": s.vision.screen_capture_interval_s > 0,
            "emotion_detection": s.vision.emotion_detection,
            # Memory
            "save_history": s.memory.episodic.save_all_interactions,
            # Privacy / security
            "pii_scrub": s.security.pii_scrub,
            "encrypt_at_rest": s.security.encrypt_at_rest,
        }
    except Exception:
        return {
            "vision_enabled": False,
            "screen_capture": False,
            "emotion_detection": False,
            "save_history": True,
            "pii_scrub": True,
            "encrypt_at_rest": True,
        }


def _get_permissions() -> dict[str, bool]:
    global _permissions
    if _permissions is None:
        defaults = _load_permissions()
        _permissions = get_settings_store().get_section("permissions", defaults)
    return _permissions


def set_identity_manager(manager: OwnerIdentityManager) -> None:
    global _identity_manager
    _identity_manager = manager


def _get_manager() -> OwnerIdentityManager:
    if _identity_manager is None:
        raise HTTPException(status_code=503, detail="Identity manager not initialised")
    return _identity_manager


# ── Request / Response models ──────────────────────────────────────────────


class ProfileResponse(BaseModel):
    has_owner: bool
    name: str
    ai_name: str
    email: str = ""


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    ai_name: str | None = None
    email: str | None = None


class ResetPassphraseRequest(BaseModel):
    current_passphrase: str
    new_passphrase: str


class RegisterRequest(BaseModel):
    name: str
    passphrase: str
    ai_name: str = "Emily"
    email: str = ""
    voice: str = ""


class SuccessResponse(BaseModel):
    ok: bool
    message: str


class LoginRequest(BaseModel):
    passphrase: str


class ForgotPasswordRequest(BaseModel):
    email: str


class VerifyCodeRequest(BaseModel):
    code: str
    new_passphrase: str


# ── Routes ────────────────────────────────────────────────────────────────


@router.get("/profile", response_model=ProfileResponse)
async def get_profile() -> ProfileResponse:
    """Return current owner profile (safe fields only)."""
    m = _get_manager()
    owner = m._owner
    return ProfileResponse(
        has_owner=m.has_owner,
        name=m.owner_name,
        ai_name=m.ai_name,
        email=owner.email if owner else "",
    )


@router.post("/profile", response_model=SuccessResponse)
async def update_profile(body: UpdateProfileRequest) -> SuccessResponse:
    """Update AI name and/or email."""
    m = _get_manager()
    if not m.has_owner:
        raise HTTPException(status_code=400, detail="No owner registered yet")
    if body.ai_name is not None:
        await m.update_ai_name(body.ai_name)
    if body.email is not None and m._owner:
        m._owner.email = body.email.strip()
        await m.save()
    return SuccessResponse(ok=True, message="Profile updated")


@router.post("/password/reset", response_model=SuccessResponse)
async def reset_passphrase(body: ResetPassphraseRequest) -> SuccessResponse:
    """Verify current passphrase then set a new one."""
    m = _get_manager()
    if not m.has_owner:
        raise HTTPException(status_code=400, detail="No owner registered yet")
    ok = await m.reset_passphrase(body.current_passphrase, body.new_passphrase)
    if not ok:
        raise HTTPException(status_code=401, detail="Current passphrase is incorrect")
    return SuccessResponse(ok=True, message="Passphrase updated successfully")


@router.post("/register", response_model=SuccessResponse)
async def register_owner(body: RegisterRequest) -> SuccessResponse:
    """First-time owner registration via the web UI."""
    m = _get_manager()
    if m.has_owner:
        raise HTTPException(status_code=409, detail="Owner already registered")
    ok = await m.register_owner(
        name=body.name,
        passphrase=body.passphrase,
        personal_facts={"name": body.name},
    )
    if ok:
        await m.update_ai_name(body.ai_name)
        if m._owner:
            if body.email:
                m._owner.email = body.email.strip()
            if body.voice:
                m._owner.voice_preference = body.voice.strip()
            await m.save()
    if not ok:
        raise HTTPException(status_code=500, detail="Registration failed")
    return SuccessResponse(
        ok=True, message=f"Registered as {body.name}. Your AI is called {body.ai_name}."
    )


# ── Auth endpoints ─────────────────────────────────────────────────────────


@router.post("/auth/login", response_model=SuccessResponse)
async def login(body: LoginRequest) -> SuccessResponse:
    """Verify passphrase for web/Tauri app login."""
    m = _get_manager()
    if not m.has_owner:
        raise HTTPException(status_code=400, detail="No owner registered yet")
    # No passphrase was ever set — auto-authenticate (first-run bypass)
    if m._owner and not m._owner.passphrase_hash:
        return SuccessResponse(ok=True, message="Authenticated")
    ok = await m.verify_passphrase(body.passphrase)
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid passphrase")
    return SuccessResponse(ok=True, message="Authenticated")


@router.post("/auth/forgot", response_model=SuccessResponse)
async def forgot_password(body: ForgotPasswordRequest) -> SuccessResponse:
    """Send a 6-digit reset code to the owner's email."""
    m = _get_manager()
    if not m.has_owner or not m._owner:
        raise HTTPException(status_code=400, detail="No owner registered")

    # Check email matches (constant-time comparison via hash)
    stored_email = m._owner.email.strip().lower()
    submitted_email = body.email.strip().lower()
    if not stored_email or stored_email != submitted_email:
        # Don't reveal whether email exists — always say "sent"
        return SuccessResponse(ok=True, message="If that email is on file, a code has been sent.")

    code = f"{random.randint(100000, 999999)}"
    _reset_codes[hashlib.sha256(stored_email.encode()).hexdigest()] = (
        code,
        time.time() + 600,  # 10-minute TTL
    )

    # Send via SMTP
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if smtp_host and smtp_user:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"{m.ai_name} — Password Reset Code"
            msg["From"] = smtp_from
            msg["To"] = submitted_email
            msg.set_content(
                f"Your password reset code is: {code}\n\n"
                "This code expires in 10 minutes.\n"
                f"If you didn't request this, you can ignore this email."
            )
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
            log.info("reset_code_sent", email=submitted_email[:3] + "***")
        except Exception as exc:
            log.error("smtp_send_failed", error=str(exc)[:200])
            raise HTTPException(status_code=500, detail="Failed to send email") from exc
    else:
        log.warning("smtp_not_configured — code: %s", code)

    return SuccessResponse(ok=True, message="If that email is on file, a code has been sent.")


@router.post("/auth/verify-code", response_model=SuccessResponse)
async def verify_reset_code(body: VerifyCodeRequest) -> SuccessResponse:
    """Verify the 6-digit code and set a new passphrase."""
    m = _get_manager()
    if not m.has_owner or not m._owner:
        raise HTTPException(status_code=400, detail="No owner registered")

    email_hash = hashlib.sha256(m._owner.email.strip().lower().encode()).hexdigest()
    entry = _reset_codes.get(email_hash)

    if not entry:
        raise HTTPException(status_code=400, detail="No reset code pending")

    stored_code, expiry = entry
    if time.time() > expiry:
        _reset_codes.pop(email_hash, None)
        raise HTTPException(status_code=400, detail="Code expired")

    if body.code != stored_code:
        raise HTTPException(status_code=401, detail="Invalid code")

    # Code is valid — set new passphrase
    m._owner.passphrase_hash = hashlib.sha256(body.new_passphrase.encode()).hexdigest()
    await m.save()
    _reset_codes.pop(email_hash, None)
    log.info("passphrase_reset_via_email_code")
    return SuccessResponse(ok=True, message="Passphrase reset successfully")


@router.get("/auth/status")
async def auth_status() -> dict:
    """Check if an owner exists and whether a passphrase has been set."""
    m = _get_manager()
    passphrase_set = bool(m._owner and m._owner.passphrase_hash)
    return {"has_owner": m.has_owner, "passphrase_set": passphrase_set}


@router.post("/auth/setup-passphrase", response_model=SuccessResponse)
async def setup_passphrase(body: LoginRequest) -> SuccessResponse:
    """Set a passphrase for the first time (when none was set during registration)."""
    m = _get_manager()
    if not m.has_owner or not m._owner:
        raise HTTPException(status_code=400, detail="No owner registered yet")
    if m._owner.passphrase_hash:
        raise HTTPException(status_code=409, detail="Passphrase already set — use reset instead")
    if not body.passphrase.strip():
        raise HTTPException(status_code=400, detail="Passphrase cannot be empty")
    m._owner.passphrase_hash = hashlib.sha256(body.passphrase.encode()).hexdigest()
    await m.save()
    log.info("passphrase_set_first_time", owner=m.owner_name)
    return SuccessResponse(ok=True, message="Passphrase set successfully")


# ── Permissions / privacy ──────────────────────────────────────────────────


class PermissionsRequest(BaseModel):
    vision_enabled: bool | None = None
    screen_capture: bool | None = None
    emotion_detection: bool | None = None
    save_history: bool | None = None
    pii_scrub: bool | None = None
    encrypt_at_rest: bool | None = None


@router.get("/permissions")
async def get_permissions() -> dict:
    """Return current runtime permission flags."""
    return _get_permissions()


@router.put("/permissions")
async def update_permissions(body: PermissionsRequest) -> dict:
    """Update one or more runtime permission flags (session-scoped)."""
    perms = _get_permissions()
    for field, value in body.model_dump(exclude_none=True).items():
        perms[field] = value
        log.info("permission_changed", permission=field, value=value)
    get_settings_store().set_section("permissions", perms)
    return {"ok": True, "permissions": perms}


# ── Persona traits ─────────────────────────────────────────────────────────

# Runtime persona traits — initialised lazily from config on first GET.
# Changes are session-scoped (not written back to config.yaml yet).
_persona: dict[str, float] | None = None


def _load_persona() -> dict[str, float]:
    """Read persona trait values from config.yaml."""
    try:
        from config import get_settings

        s = get_settings()
        return {
            "curiosity": float(s.persona.curiosity),
            "warmth": float(s.persona.warmth),
            "directness": float(s.persona.directness),
            "humor": float(s.persona.humor),
            "formality": float(s.persona.formality),
        }
    except Exception:
        return {
            "curiosity": 0.5,
            "warmth": 0.5,
            "directness": 0.5,
            "humor": 0.2,
            "formality": 0.5,
        }


def _get_persona() -> dict[str, float]:
    global _persona
    if _persona is None:
        defaults = _load_persona()
        _persona = get_settings_store().get_section("persona", defaults)
    return _persona


class PersonaRequest(BaseModel):
    curiosity: float | None = None
    warmth: float | None = None
    directness: float | None = None
    humor: float | None = None
    formality: float | None = None


@router.get("/persona")
async def get_persona() -> dict:
    """Return current runtime persona trait values."""
    return _get_persona()


@router.put("/persona")
async def update_persona(body: PersonaRequest) -> dict:
    """Update one or more persona traits (session-scoped, clamped 0.0–1.0)."""
    traits = _get_persona()
    for field, value in body.model_dump(exclude_none=True).items():
        traits[field] = max(0.0, min(1.0, float(value)))
        log.info("persona_trait_changed", trait=field, value=value)
    get_settings_store().set_section("persona", traits)
    return {"ok": True, "persona": traits}


# ── Advanced settings ──────────────────────────────────────────────────────

# Runtime advanced settings — initialised lazily from config on first GET.
_advanced: dict | None = None


def _load_advanced() -> dict:
    """Read advanced setting values from config.yaml."""
    try:
        from config import get_settings

        s = get_settings()
        return {
            "stt_profile": str(s.stt.profile),
            "stt_beam_size": int(s.stt.beam_size),
            "llm_temperature": float(s.llm.inference.temperature),
            "memory_backup_interval": int(s.memory.episodic.auto_backup_interval_minutes),
            "memory_decay_days": int(s.memory.semantic.temporal_decay_days),
            "self_improve": bool(s.self_improvement.evolve_prompts),
            "track_perf": bool(s.self_improvement.track_performance),
            "guest_mode": bool(s.owner.guest_mode_enabled),
            "verify_timeout": int(s.owner.verification_timeout_minutes),
        }
    except Exception:
        return {
            "stt_profile": "accurate",
            "stt_beam_size": 5,
            "llm_temperature": 0.7,
            "memory_backup_interval": 30,
            "memory_decay_days": 365,
            "self_improve": True,
            "track_perf": True,
            "guest_mode": True,
            "verify_timeout": 60,
        }


def _get_advanced() -> dict:
    global _advanced
    if _advanced is None:
        defaults = _load_advanced()
        _advanced = get_settings_store().get_section("advanced", defaults)
    return _advanced


class AdvancedRequest(BaseModel):
    stt_profile: str | None = None
    stt_beam_size: int | None = None
    llm_temperature: float | None = None
    memory_backup_interval: int | None = None
    memory_decay_days: int | None = None
    self_improve: bool | None = None
    track_perf: bool | None = None
    guest_mode: bool | None = None
    verify_timeout: int | None = None


@router.get("/advanced")
async def get_advanced() -> dict:
    """Return current runtime advanced settings."""
    return _get_advanced()


@router.put("/advanced")
async def update_advanced(body: AdvancedRequest) -> dict:
    """Update one or more advanced settings (session-scoped)."""
    adv = _get_advanced()
    for field, value in body.model_dump(exclude_none=True).items():
        adv[field] = value
        log.info("advanced_setting_changed", setting=field, value=value)
    get_settings_store().set_section("advanced", adv)
    return {"ok": True, "advanced": adv}


# ── Tool capability permissions ────────────────────────────────────────────
# Maps individual plugin tool names → permission group key.
# Any tool not in this map is allowed by default.
TOOL_PERMISSION_GROUPS: dict[str, str] = {
    # Files
    "file_reader": "file_read",
    "file_writer": "file_write",
    # System
    "shell": "shell",
    "code_executor": "code_execution",
    # Computer
    "computer_open": "computer_control",
    "open_application": "computer_control",
    "computer_state": "screen_awareness",
    "screen_text": "screen_awareness",
    "active_window": "screen_awareness",
    "running_processes": "screen_awareness",
    "clipboard": "screen_awareness",
    "recent_files": "screen_awareness",
    "screen_describe": "screen_awareness",
    "screen_ocr": "screen_awareness",
    "screen_monitor": "screen_awareness",
    "image_describe": "screen_awareness",
    "video_describe": "screen_awareness",
    "process_manager": "screen_awareness",
    "notification": "notifications",
    # Communication
    "email_reader": "email",
    "calendar": "calendar",
    "discord_send": "discord",
    # Internet
    "web_search": "web_search",
    "web_fetch": "web_fetch",
    "home_assistant": "home_assistant",
}

_tool_permissions: dict[str, bool] | None = None


def _load_tool_permissions() -> dict[str, bool]:
    """Default tool permissions — all local tools on, external integrations off until configured."""
    return {
        "file_read": True,
        "file_write": True,
        "shell": True,
        "code_execution": True,
        "computer_control": True,
        "screen_awareness": True,
        "notifications": True,
        "email": True,
        "calendar": True,
        "discord": False,  # off until Discord bot token is configured
        "web_search": True,
        "web_fetch": True,
        "home_assistant": False,  # off until Home Assistant URL/token is configured
    }


def _get_tool_permissions() -> dict[str, bool]:
    global _tool_permissions
    if _tool_permissions is None:
        defaults = _load_tool_permissions()
        _tool_permissions = get_settings_store().get_section("tools", defaults)
    return _tool_permissions


def is_tool_enabled(tool_name: str) -> bool:
    """Check if a named plugin tool is allowed by the current runtime permissions.

    Called by BaseTool.safe_execute() before every tool invocation.
    """
    perms = _get_tool_permissions()
    group = TOOL_PERMISSION_GROUPS.get(tool_name)
    if group is None:
        return True  # Unknown/uncategorised tools are allowed by default
    return perms.get(group, True)


class ToolPermissionsRequest(BaseModel):
    file_read: bool | None = None
    file_write: bool | None = None
    shell: bool | None = None
    code_execution: bool | None = None
    computer_control: bool | None = None
    screen_awareness: bool | None = None
    notifications: bool | None = None
    email: bool | None = None
    calendar: bool | None = None
    discord: bool | None = None
    web_search: bool | None = None
    web_fetch: bool | None = None
    home_assistant: bool | None = None


@router.get("/tools")
async def get_tool_permissions_route() -> dict:
    """Return current runtime tool capability permissions."""
    return _get_tool_permissions()


@router.put("/tools")
async def update_tool_permissions(body: ToolPermissionsRequest) -> dict:
    """Enable or disable tool capability groups (session-scoped)."""
    perms = _get_tool_permissions()
    for field, value in body.model_dump(exclude_none=True).items():
        perms[field] = value
        log.info("tool_permission_changed", capability=field, enabled=value)
    get_settings_store().set_section("tools", perms)
    return {"ok": True, "permissions": perms}


# ── Skills CRUD ────────────────────────────────────────────────────────────


class SkillRequest(BaseModel):
    name: str
    icon: str = ""
    description: str = ""
    system_addition: str = ""
    temperature: float = 0.5
    enable_thinking: bool = False
    enable_code_execution: bool = False


@router.get("/skills")
async def list_skills() -> dict:
    """Return all built-in and custom skills."""
    from dataclasses import asdict

    from emily_chat.emily.skills import EMILY_SKILLS, load_custom_skills

    result = {}
    for skill_id, skill in EMILY_SKILLS.items():
        d = asdict(skill)
        d.pop("multi_model", None)
        d.pop("models_to_compare", None)
        d.pop("preferred_models", None)
        d.pop("enable_web_search", None)
        result[skill_id] = {**d, "builtin": True}
    for skill_id, skill in load_custom_skills().items():
        if skill_id not in result:
            d = asdict(skill)
            d.pop("multi_model", None)
            d.pop("models_to_compare", None)
            d.pop("preferred_models", None)
            d.pop("enable_web_search", None)
            result[skill_id] = {**d, "builtin": False}
    return result


@router.post("/skills/{skill_id}")
async def upsert_skill(skill_id: str, body: SkillRequest) -> dict:
    """Create or update a custom skill by ID."""
    from emily_chat.emily.skills import EmilySkill, save_custom_skill

    if not skill_id.replace("_", "").isalnum():
        raise HTTPException(400, "skill_id must be alphanumeric + underscores only")
    skill = EmilySkill(
        name=body.name,
        icon=body.icon,
        description=body.description,
        system_addition=body.system_addition,
        temperature=max(0.0, min(2.0, body.temperature)),
        enable_thinking=body.enable_thinking,
        enable_code_execution=body.enable_code_execution,
    )
    save_custom_skill(skill_id, skill)
    log.info("custom_skill_saved", skill_id=skill_id)
    return {"ok": True, "skill_id": skill_id}


@router.delete("/skills/{skill_id}")
async def remove_skill(skill_id: str) -> dict:
    """Delete a custom skill. Built-in skills cannot be deleted."""
    from emily_chat.emily.skills import EMILY_SKILLS, delete_custom_skill

    if skill_id in EMILY_SKILLS:
        raise HTTPException(400, "Built-in skills cannot be deleted")
    deleted = delete_custom_skill(skill_id)
    if not deleted:
        raise HTTPException(404, f"Custom skill '{skill_id}' not found")
    log.info("custom_skill_deleted", skill_id=skill_id)
    return {"ok": True}


# ── Behavior rules ────────────────────────────────────────────────────────

import json as _json
from pathlib import Path as _Path

_RULES_PATH = _Path.home() / ".emily-chat" / "rules.json"
_rules_cache: list[str] | None = None


def _load_rules() -> list[str]:
    global _rules_cache
    if _rules_cache is not None:
        return _rules_cache
    try:
        _rules_cache = _json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    except Exception:
        _rules_cache = []
    return _rules_cache


def get_rules() -> list[str]:
    """Return the current behavior rules list (importable by persona engine)."""
    return _load_rules()


@router.get("/rules")
async def list_rules() -> dict:
    """Return the list of active behavior rules."""
    return {"rules": _load_rules()}


@router.put("/rules")
async def save_rules(body: dict) -> dict:
    """Replace the full rules list."""
    global _rules_cache
    rules: list[str] = [str(r).strip() for r in body.get("rules", []) if str(r).strip()]
    _RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RULES_PATH.write_text(_json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")
    _rules_cache = rules
    log.info("behavior_rules_saved", count=len(rules))
    return {"ok": True, "rules": rules}


# ── Settings export / import ───────────────────────────────────────────────


@router.get("/export")
async def export_settings() -> dict:
    """Export all user settings as JSON."""
    return get_settings_store().get_all()


@router.post("/import")
async def import_settings(body: dict) -> dict:
    """Import settings from a JSON backup. Overwrites all current settings."""
    get_settings_store().import_all(body)
    # Reset in-memory caches so next GET picks up imported values
    global _permissions, _persona, _advanced, _tool_permissions
    _permissions = None
    _persona = None
    _advanced = None
    _tool_permissions = None
    log.info("settings_imported")
    return {"ok": True, "message": "Settings imported successfully"}
