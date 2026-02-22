"""Emily's built-in skill definitions and custom skill persistence.

Each skill injects additional system-prompt instructions that shape Emily's
behaviour for a particular task type.  Skills do NOT change her identity —
only her approach.

Custom skills are stored in ``~/.emily-chat/custom_skills.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EmilySkill:
    """A named behaviour mode that augments Emily's system prompt."""

    name: str
    icon: str = ""
    description: str = ""
    system_addition: str = ""
    enable_thinking: bool = False
    enable_web_search: bool = False
    enable_code_execution: bool = False
    multi_model: bool = False
    models_to_compare: list[str] = field(default_factory=list)
    preferred_models: list[str] = field(default_factory=list)
    temperature: float = 0.5


EMILY_SKILLS: dict[str, EmilySkill] = {
    "deep_think": EmilySkill(
        name="Deep Think",
        icon="\U0001f9e0",
        description="Emily reasons step-by-step before answering",
        system_addition=(
            "Before responding, reason through the problem. "
            "Show your thinking. Consider multiple angles. Be explicit about "
            "uncertainty. Prefer depth over speed."
        ),
        enable_thinking=True,
        preferred_models=["claude-opus-4-5", "o3", "deepseek-r2", "groq-deepseek-r1"],
        temperature=0.3,
    ),
    "code": EmilySkill(
        name="Code",
        icon="\U0001f4bb",
        description="Emily writes, reviews, and debugs code",
        system_addition=(
            "You are an expert programmer across all languages. "
            "Write clean, well-commented, production-quality code. Explain what "
            "the code does and why design decisions were made. Flag edge cases, "
            "security issues, and performance concerns. Always specify the "
            "language in code blocks."
        ),
        enable_thinking=True,
        enable_code_execution=True,
        preferred_models=["claude-opus-4-5", "codestral-2", "deepseek-v3-2", "o4-mini"],
        temperature=0.1,
    ),
    "research": EmilySkill(
        name="Research",
        icon="\U0001f52c",
        description="Emily searches the web and synthesizes sources",
        system_addition=(
            "Use the web search results provided. Cite all "
            "factual claims with inline [1][2] markers. Distinguish what sources "
            "say from your own synthesis. Note when sources conflict or are "
            "outdated. Provide a confidence level for key claims."
        ),
        enable_web_search=True,
        enable_thinking=True,
        preferred_models=["claude-sonnet-4-5", "gemini-3-pro", "gpt-5", "groq-deepseek-r1"],
        temperature=0.2,
    ),
    "writing": EmilySkill(
        name="Writing",
        icon="\u270d\ufe0f",
        description="Emily writes and edits with craft and style",
        system_addition=(
            "You are a skilled writer and editor. Match the "
            "requested tone and style exactly. When editing: explain what you "
            "changed and why. When writing original content: ask clarifying "
            "questions if the purpose or audience is unclear. Prefer concrete, "
            "vivid language over abstract generalities."
        ),
        preferred_models=["grok-4-1", "gpt-5-2", "claude-opus-4-5"],
        temperature=0.8,
    ),
    "concise": EmilySkill(
        name="Concise",
        icon="\u26a1",
        description="Emily keeps it short and sharp",
        system_addition=(
            "Be maximally concise. 1-3 sentences when possible. "
            "No preamble. No summary. No padding. Just the answer. If the "
            "question genuinely requires a longer answer, warn the user first: "
            '"This needs a longer answer \u2014 want the full version?".'
        ),
        preferred_models=["claude-haiku-4-5", "gpt-4o-mini", "groq-llama-70b", "gemini-3-flash"],
        temperature=0.3,
    ),
    "analyst": EmilySkill(
        name="Analyst",
        icon="\U0001f4ca",
        description="Emily breaks down complexity systematically",
        system_addition=(
            "Structure analysis: context \u2192 key factors \u2192 "
            "analysis \u2192 implications \u2192 conclusion. Use frameworks (SWOT, "
            "first principles, etc.) where applicable. Quantify wherever "
            "possible. Separate facts from assumptions from inferences. "
            "Explicitly state uncertainty levels."
        ),
        enable_thinking=True,
        preferred_models=["claude-opus-4-5", "o3", "gemini-3-pro", "gpt-5"],
        temperature=0.2,
    ),
    "tutor": EmilySkill(
        name="Tutor",
        icon="\U0001f393",
        description="Emily teaches through questions and examples",
        system_addition=(
            "Teach using the Socratic method. Use analogies "
            "and concrete examples always. Check understanding with follow-up "
            "questions. Calibrate explanation depth to the user's demonstrated "
            "knowledge. Don't just give answers if the goal is understanding."
        ),
        temperature=0.6,
    ),
    "brainstorm": EmilySkill(
        name="Brainstorm",
        icon="\U0001f4a1",
        description="Emily generates bold, diverse ideas",
        system_addition=(
            "Generate maximum diverse ideas without "
            "self-censoring. Include unconventional, contrarian, and "
            "unexpected ideas alongside obvious ones. Quantity first, "
            "then group by theme. Build on constraints rather than "
            "around them."
        ),
        temperature=1.0,
    ),
    "debate": EmilySkill(
        name="Devil's Advocate",
        icon="\U0001f608",
        description="Emily argues the strongest opposing position",
        system_addition=(
            "Take the strongest possible position AGAINST "
            "whatever the user says or believes. Find non-obvious counterarguments. "
            "Be intellectually honest: acknowledge strong points before countering. "
            "Don't capitulate just because the user pushes back."
        ),
        temperature=0.7,
    ),
    "translate": EmilySkill(
        name="Translate",
        icon="\U0001f30d",
        description="Emily translates between any languages",
        system_addition=(
            "Auto-detect source language. Provide natural, "
            "idiomatic translations \u2014 not literal word-for-word. Note "
            "culturally-specific terms that don't translate cleanly. If "
            "requested, show original alongside translation."
        ),
        preferred_models=["qwen3-235b", "gpt-5", "mistral-large-3", "gemini-3-flash"],
        temperature=0.1,
    ),
    "eli5": EmilySkill(
        name="Simple (ELI5)",
        icon="\U0001f9d2",
        description="Emily explains anything simply",
        system_addition=(
            "Explain as if to a curious, bright 12-year-old. "
            "Use everyday analogies. Zero unexplained jargon. One idea per "
            "sentence. Short paragraphs. If something genuinely can't be "
            "simplified without losing accuracy, say so explicitly."
        ),
        temperature=0.6,
    ),
    "compare": EmilySkill(
        name="Compare Models",
        icon="\u2696\ufe0f",
        description="Send the same message to multiple Emily engines simultaneously",
        multi_model=True,
        models_to_compare=["claude-sonnet-4-5", "gpt-5", "gemini-3-flash"],
    ),
}


_CUSTOM_SKILLS_PATH = Path.home() / ".emily-chat" / "custom_skills.json"


def get_skill(skill_id: str) -> EmilySkill | None:
    """Look up a built-in or custom skill by its ID.

    Checks built-in skills first, then falls back to custom skills.

    Args:
        skill_id: Key into ``EMILY_SKILLS`` or custom skills
            (e.g. ``"deep_think"``).

    Returns:
        The matching :class:`EmilySkill`, or ``None`` if not found.
    """
    skill = EMILY_SKILLS.get(skill_id)
    if skill is not None:
        return skill
    custom = load_custom_skills()
    return custom.get(skill_id)


def load_custom_skills(path: Path | None = None) -> dict[str, EmilySkill]:
    """Load user-defined skills from the JSON file.

    Args:
        path: Override path for testing; defaults to
            ``~/.emily-chat/custom_skills.json``.

    Returns:
        Dict of ``{skill_id: EmilySkill}``.
    """
    p = path or _CUSTOM_SKILLS_PATH
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        result: dict[str, EmilySkill] = {}
        for skill_id, obj in data.items():
            obj.pop("models_to_compare", None)
            obj.pop("preferred_models", None)
            obj.pop("multi_model", None)
            result[skill_id] = EmilySkill(**obj)
        return result
    except (json.JSONDecodeError, TypeError, KeyError):
        return {}


def save_custom_skill(
    skill_id: str,
    skill: EmilySkill,
    path: Path | None = None,
) -> None:
    """Persist a user-defined skill to the JSON file.

    Args:
        skill_id: Unique identifier for the skill.
        skill: The :class:`EmilySkill` to save.
        path: Override path for testing.
    """
    p = path or _CUSTOM_SKILLS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = load_custom_skills(p)
    existing[skill_id] = skill
    serializable: dict[str, dict] = {}
    for sid, s in existing.items():
        d = asdict(s)
        d.pop("models_to_compare", None)
        d.pop("preferred_models", None)
        d.pop("multi_model", None)
        serializable[sid] = d
    p.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_custom_skill(skill_id: str, path: Path | None = None) -> bool:
    """Remove a custom skill from the JSON file.

    Args:
        skill_id: The skill to remove.
        path: Override path for testing.

    Returns:
        ``True`` if the skill was found and removed.
    """
    p = path or _CUSTOM_SKILLS_PATH
    existing = load_custom_skills(p)
    if skill_id not in existing:
        return False
    del existing[skill_id]
    serializable = {sid: asdict(s) for sid, s in existing.items()}
    p.write_text(json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def get_all_skills(custom_path: Path | None = None) -> dict[str, EmilySkill]:
    """Merge built-in and custom skills into a single dict.

    Built-in skills take precedence over custom skills with the same ID.

    Args:
        custom_path: Override path for testing.

    Returns:
        Combined dict of ``{skill_id: EmilySkill}``.
    """
    merged = dict(load_custom_skills(custom_path))
    merged.update(EMILY_SKILLS)
    return merged
