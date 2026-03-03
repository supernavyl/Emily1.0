"""Model registry, skills, profiles, and settings routes for the React frontend."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1", tags=["models"])


_ENV_KEY_MAP: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "together": "TOGETHER_API_KEY",
    "xai": "XAI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


@router.get("/models")
async def list_models():
    """Return the full model registry grouped by provider."""
    from emily_chat.models.registry import EMILY_MODEL_REGISTRY

    models = {}
    for key, spec in EMILY_MODEL_REGISTRY.items():
        models[key] = {
            "key": key,
            "display": spec.display,
            "provider": spec.provider,
            "model_id": spec.model_id,
            "context": spec.context,
            "thinking": spec.thinking,
            "vision": spec.vision,
            "audio": spec.audio,
            "video": spec.video,
            "input_usd": spec.input_usd,
            "output_usd": spec.output_usd,
            "speed": spec.speed,
            "tier": spec.tier,
            "default": spec.default,
            "open_weights": spec.open_weights,
            "best_for": spec.best_for,
            "notes": spec.notes,
            "reasoning_effort": spec.reasoning_effort,
        }
    return {"models": models}


@router.get("/models/providers")
async def list_providers():
    """Return provider availability (which API keys are configured)."""
    providers = {}
    for provider, env_var in _ENV_KEY_MAP.items():
        providers[provider] = {
            "available": bool(os.environ.get(env_var)),
            "env_var": env_var,
        }
    providers["ollama"] = {"available": True, "env_var": None}
    providers["llamacpp"] = {"available": True, "env_var": None}
    return {"providers": providers}


# ── Modes endpoints ───────────────────────────────────────────────


@router.get("/modes")
async def list_modes():
    """Return all operational modes (built-in + custom)."""
    from modes.engine import get_mode_engine

    engine = get_mode_engine()
    all_modes = engine.list_all()
    return {
        "modes": {
            mid: {
                "id": mid,
                "name": m.name,
                "display": m.display,
                "icon": m.icon,
                "description": m.description,
                "reasoning_strategy": m.reasoning_strategy,
                "reasoning_depth": m.reasoning_depth,
                "enable_rag": m.enable_rag,
                "enable_web_search": m.enable_web_search,
                "enable_tools": m.enable_tools,
                "enable_critic": m.enable_critic,
                "enable_thinking": m.enable_thinking,
                "built_in": engine.is_builtin(mid),
            }
            for mid, m in all_modes.items()
        }
    }


@router.get("/modes/{mode_id}")
async def get_mode_detail(mode_id: str):
    """Return full mode configuration."""
    from modes.engine import ModeEngine, get_mode_engine

    engine = get_mode_engine()
    mode = engine.get(mode_id)
    if mode.name == "normal" and mode_id != "normal":
        raise HTTPException(404, f"Mode '{mode_id}' not found")
    return {"mode": ModeEngine.mode_to_dict(mode), "id": mode_id}


class ModeCreate(BaseModel):
    name: str
    display: str
    icon: str = ""
    description: str = ""
    tier_preference: list[str] = Field(default_factory=list)
    reasoning_strategy: str = "direct"
    reasoning_depth: int = 1
    temperature_override: float | None = None
    max_tokens_override: int | None = None
    enable_rag: bool = True
    enable_web_search: bool = False
    enable_tools: bool = True
    enable_critic: bool = False
    enable_thinking: bool = False


@router.post("/modes", status_code=201)
async def create_mode(mode_id: str, body: ModeCreate):
    """Create a custom mode."""
    from modes.engine import OperationalMode, get_mode_engine

    engine = get_mode_engine()
    mode = OperationalMode(**body.model_dump())
    try:
        engine.create_custom(mode_id, mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "id": mode_id}


@router.put("/modes/{mode_id}")
async def update_mode(mode_id: str, body: ModeCreate):
    """Update a custom mode (built-in modes cannot be modified)."""
    from modes.engine import OperationalMode, get_mode_engine

    engine = get_mode_engine()
    if engine.is_builtin(mode_id):
        raise HTTPException(400, "Cannot modify built-in modes")
    mode = OperationalMode(**body.model_dump())
    engine.create_custom(mode_id, mode)
    return {"ok": True, "id": mode_id}


# ── Rules endpoints ──────────────────────────────────────────────


@router.get("/rules")
async def list_rules():
    """Return all rules (built-in + custom)."""
    from rules.engine import RulesEngine, get_rules_engine

    engine = get_rules_engine()
    all_rules = engine.list_all()
    return {
        "rules": {
            rid: {
                **RulesEngine.rule_to_dict(r),
                "built_in": engine.is_builtin(rid),
            }
            for rid, r in all_rules.items()
        }
    }


class RuleCreate(BaseModel):
    id: str
    name: str
    scope: str = "global"
    trigger: str = "always"
    condition: str = ""
    action: str = "log"
    payload: str = ""
    priority: int = 50
    enabled: bool = True


@router.post("/rules", status_code=201)
async def create_rule(body: RuleCreate):
    """Create a custom rule."""
    from rules.engine import Rule, get_rules_engine

    engine = get_rules_engine()
    rule = Rule(**body.model_dump())
    try:
        engine.create_custom(rule)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "id": rule.id}


@router.put("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleCreate):
    """Update a custom rule."""
    from rules.engine import get_rules_engine

    engine = get_rules_engine()
    if engine.is_builtin(rule_id):
        raise HTTPException(400, "Cannot modify built-in rules")
    try:
        updated = engine.update_custom(rule_id, body.model_dump())
    except KeyError:
        raise HTTPException(404, f"Rule '{rule_id}' not found")
    return {"ok": True, "rule": engine.rule_to_dict(updated)}


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str):
    """Delete a custom rule."""
    from rules.engine import get_rules_engine

    engine = get_rules_engine()
    if engine.is_builtin(rule_id):
        raise HTTPException(400, "Cannot delete built-in rules")
    deleted = engine.delete_custom(rule_id)
    if not deleted:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


# ── Skills endpoints ─────────────────────────────────────────────


@router.get("/skills")
async def list_skills():
    """Return all built-in and custom skills."""
    from emily_chat.emily.skills import EMILY_SKILLS, get_all_skills

    all_skills = get_all_skills()
    result = {}
    for sid, skill in all_skills.items():
        result[sid] = {
            "id": sid,
            "name": skill.name,
            "icon": skill.icon,
            "description": skill.description,
            "enable_thinking": skill.enable_thinking,
            "enable_web_search": skill.enable_web_search,
            "enable_code_execution": skill.enable_code_execution,
            "temperature": skill.temperature,
            "built_in": sid in EMILY_SKILLS,
            "has_pipeline": skill.has_pipeline,
            "pipeline_steps": [s.name for s in skill.pipeline] if skill.pipeline else [],
            "compatible_modes": skill.compatible_modes,
        }
    return {"skills": result}


class SkillCreate(BaseModel):
    name: str
    icon: str = ""
    description: str = ""
    system_addition: str = ""
    enable_thinking: bool = False
    enable_web_search: bool = False
    enable_code_execution: bool = False
    temperature: float = 0.5


@router.post("/skills", status_code=201)
async def create_skill(skill_id: str, body: SkillCreate):
    from emily_chat.emily.skills import EmilySkill, save_custom_skill

    skill = EmilySkill(
        name=body.name,
        icon=body.icon,
        description=body.description,
        system_addition=body.system_addition,
        enable_thinking=body.enable_thinking,
        enable_web_search=body.enable_web_search,
        enable_code_execution=body.enable_code_execution,
        temperature=body.temperature,
    )
    save_custom_skill(skill_id, skill)
    return {"ok": True, "id": skill_id}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    from emily_chat.emily.skills import EMILY_SKILLS, delete_custom_skill

    if skill_id in EMILY_SKILLS:
        raise HTTPException(400, "Cannot delete built-in skills")
    deleted = delete_custom_skill(skill_id)
    if not deleted:
        raise HTTPException(404, "Skill not found")
    return {"ok": True}


@router.get("/profiles")
async def list_profiles():
    from emily_chat.profiles import EMILY_PROFILE_ROLES, load_profiles

    profiles = load_profiles()
    return {
        "profiles": [p.model_dump() for p in profiles],
        "roles": [{"key": k, "label": v} for k, v in EMILY_PROFILE_ROLES],
    }


class ProfileCreate(BaseModel):
    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    roles: dict[str, str] = Field(default_factory=dict)


@router.post("/profiles", status_code=201)
async def create_profile(body: ProfileCreate):
    from emily_chat.profiles import EmilyProfile, load_profiles, save_profiles

    profiles = load_profiles()
    profile = EmilyProfile(id=body.id, name=body.name, roles=body.roles)
    profiles.append(profile)
    save_profiles(profiles)
    return profile.model_dump()


@router.patch("/profiles/{profile_id}")
async def update_profile(profile_id: str, body: ProfileCreate):
    from emily_chat.profiles import EmilyProfile, load_profiles, save_profiles

    profiles = load_profiles()
    for i, p in enumerate(profiles):
        if p.id == profile_id:
            profiles[i] = EmilyProfile(id=profile_id, name=body.name, roles=body.roles)
            save_profiles(profiles)
            return profiles[i].model_dump()
    raise HTTPException(404, "Profile not found")


@router.delete("/profiles/{profile_id}")
async def delete_profile(profile_id: str):
    from emily_chat.profiles import load_profiles, save_profiles

    if profile_id == "default":
        raise HTTPException(400, "Cannot delete default profile")
    profiles = load_profiles()
    profiles = [p for p in profiles if p.id != profile_id]
    save_profiles(profiles)
    return {"ok": True}


@router.get("/settings")
async def get_settings():
    from emily_chat.config import load_settings

    s = load_settings()
    return s.model_dump()


class SettingsPatch(BaseModel):
    theme: str | None = None
    font_size: int | None = None
    default_model: str | None = None
    active_skill_id: str | None = None
    active_profile_id: str | None = None
    right_panel_visible: bool | None = None


@router.patch("/settings")
async def update_settings(body: SettingsPatch):
    from emily_chat.config import load_settings, save_settings

    s = load_settings()
    for key, val in body.model_dump(exclude_none=True).items():
        if hasattr(s, key):
            setattr(s, key, val)
    save_settings(s)
    return s.model_dump()
