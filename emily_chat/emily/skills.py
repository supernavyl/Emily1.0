"""Emily's built-in skill definitions and custom skill persistence.

Each skill injects additional system-prompt instructions that shape Emily's
behaviour for a particular task type.  Skills do NOT change her identity —
only her approach.

Skills 2.0 adds **execution pipelines** — multi-step workflows where each
step uses a specific model tier and passes context forward.  A skill with an
empty pipeline behaves exactly like the v1 single-shot prompt injection.

Custom skills are stored in ``~/.emily-chat/custom_skills.json``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# ── Pipeline step definition ─────────────────────────────────────


@dataclass(frozen=True)
class PipelineStep:
    """A single step in a skill's execution pipeline."""

    name: str
    tier: str
    prompt_key: str
    max_tokens: int = 4096
    pass_context_from: str = ""


# ── Skill dataclass (v2) ─────────────────────────────────────────


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

    # ── Skills 2.0 fields ─────────────────────────────────────────
    pipeline: list[PipelineStep] = field(default_factory=list)
    compatible_modes: list[str] = field(default_factory=list)
    sub_skills: list[str] = field(default_factory=list)
    track_performance: bool = True

    @property
    def has_pipeline(self) -> bool:
        """True if this skill defines a multi-step execution pipeline."""
        return len(self.pipeline) > 0


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
        preferred_models=["emily-deep-think", "o3", "deepseek-r2", "groq-deepseek-r1"],
        temperature=0.3,
        pipeline=[
            PipelineStep(name="decompose", tier="fast", prompt_key="decompose"),
            PipelineStep(
                name="reason",
                tier="deep_think",
                prompt_key="reasoning",
                max_tokens=8192,
                pass_context_from="decompose",
            ),
            PipelineStep(
                name="critique",
                tier="cloud_best",
                prompt_key="critique",
                pass_context_from="reason",
            ),
            PipelineStep(
                name="revise",
                tier="deep_think",
                prompt_key="synthesize",
                max_tokens=8192,
                pass_context_from="critique",
            ),
        ],
        compatible_modes=["normal", "deep_think", "analytical", "research"],
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
        preferred_models=["emily-code", "codestral-2", "deepseek-v3-2", "o4-mini"],
        temperature=0.1,
        pipeline=[
            PipelineStep(name="plan", tier="smart", prompt_key="decompose"),
            PipelineStep(
                name="implement",
                tier="code",
                prompt_key="code_implement",
                max_tokens=8192,
                pass_context_from="plan",
            ),
            PipelineStep(
                name="review",
                tier="reasoning",
                prompt_key="critique",
                pass_context_from="implement",
            ),
            PipelineStep(
                name="refine",
                tier="code",
                prompt_key="code_implement",
                max_tokens=8192,
                pass_context_from="review",
            ),
        ],
        compatible_modes=["normal", "code", "analytical"],
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
        preferred_models=["emily-reasoning", "emily-deep-think", "groq-deepseek-r1"],
        temperature=0.2,
        pipeline=[
            PipelineStep(name="decompose", tier="fast", prompt_key="decompose"),
            PipelineStep(
                name="search", tier="fast", prompt_key="web_search", pass_context_from="decompose"
            ),
            PipelineStep(
                name="analyze",
                tier="reasoning",
                prompt_key="reasoning",
                max_tokens=6144,
                pass_context_from="search",
            ),
            PipelineStep(
                name="synthesize",
                tier="smart",
                prompt_key="synthesize",
                max_tokens=6144,
                pass_context_from="analyze",
            ),
            PipelineStep(
                name="critique",
                tier="reasoning",
                prompt_key="critique",
                pass_context_from="synthesize",
            ),
        ],
        compatible_modes=["normal", "research", "analytical", "deep_think"],
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
        preferred_models=["emily-fast", "grok-4-1"],
        temperature=0.8,
    ),
    "voice": EmilySkill(
        name="Voice",
        icon="🎙️",
        description="Emily speaks naturally in live voice conversation",
        system_addition=(
            "You are in a LIVE VOICE CONVERSATION — not a text chat. "
            "Respond exactly like a warm, present person talking, not a chatbot typing.\n\n"
            "VOICE RULES (non-negotiable):\n"
            "- Never use markdown, bullet points, headers, numbered lists, asterisks, "
            "code blocks, or any formatting symbols — they are meaningless noise in audio.\n"
            "- Give ONE complete, flowing response. Do not fragment your answer "
            "into separate short reactions like 'Great!' followed by 'What's on your mind?' "
            "— say it all in one natural turn.\n"
            "- 2–4 sentences is the natural length for most voice replies. "
            "Never give a one-word or one-fragment answer unless it is the complete, "
            "entire, socially appropriate response.\n"
            "- Use contractions (it's, I'm, you're, that's) and natural spoken language.\n"
            "- Listen to the *social and emotional intent* behind what the person says, "
            "not just the literal words. If they're being playful, be playful back. "
            "If they seem frustrated or conflicted, acknowledge that first before responding.\n"
            "- Speak in a conversational register: warm, direct, human.\n"
            "- Spell out numbers and abbreviations as you would say them aloud.\n"
            "- If you need to think through something complex, say so out loud "
            "('Let me think about that for a second') rather than going silent."
        ),
        temperature=0.75,
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
        preferred_models=["emily-voice-fast", "groq-llama-70b"],
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
        preferred_models=["emily-reasoning", "emily-deep-think", "o3"],
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
        pipeline=[
            PipelineStep(name="position_a", tier="smart", prompt_key="debate_position"),
            PipelineStep(
                name="position_b",
                tier="smart",
                prompt_key="debate_counter",
                pass_context_from="position_a",
            ),
            PipelineStep(
                name="compare",
                tier="reasoning",
                prompt_key="critique",
                pass_context_from="position_b",
            ),
            PipelineStep(
                name="synthesize",
                tier="smart",
                prompt_key="synthesize",
                pass_context_from="compare",
            ),
        ],
        compatible_modes=["normal", "debate", "analytical"],
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
        preferred_models=["emily-smart", "qwen3-235b", "mistral-large-3"],
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
        models_to_compare=["claude-sonnet-4-6", "gpt-5", "gemini-3-flash"],
    ),
    "ad_copywriter": EmilySkill(
        name="Ad Copywriter",
        icon="\U0001f4dd",
        description="Emily writes high-converting ad copy for any platform",
        system_addition=(
            "You are a world-class direct-response copywriter. Generate "
            "ad creatives that stop scrolling and drive action. Use proven "
            "frameworks: AIDA, PAS, BAB. Write platform-specific copy "
            "(Meta, TikTok, Google, YouTube). Always provide multiple "
            "variations with different hooks. Be specific, benefit-driven, "
            "and create urgency without being sleazy."
        ),
        enable_thinking=True,
        preferred_models=["emily-fast", "emily-reasoning", "grok-4-1"],
        temperature=0.85,
    ),
    "social_media": EmilySkill(
        name="Social Media",
        icon="\U0001f4f1",
        description="Emily creates engaging social media content and strategies",
        system_addition=(
            "You are a social media strategist and content creator. "
            "Understand platform algorithms, trending formats, and audience "
            "psychology. Create content that drives engagement — hooks, "
            "captions, hashtag strategies, posting schedules. Think like a "
            "growth hacker: every post should have a clear goal. Adapt tone "
            "per platform: professional for LinkedIn, casual for TikTok, "
            "visual-first for Instagram."
        ),
        enable_web_search=True,
        preferred_models=["emily-fast", "emily-smart"],
        temperature=0.8,
    ),
    "video_script": EmilySkill(
        name="Video Script",
        icon="\U0001f3ac",
        description="Emily writes video scripts optimized for engagement",
        system_addition=(
            "You are a video scriptwriter specializing in short-form "
            "content (TikTok, Reels, Shorts) and long-form YouTube. "
            "Structure every script with: hook (first 3 seconds), "
            "problem/story, solution/value, CTA. Use pattern interrupts, "
            "open loops, and emotional triggers. Include timing notes, "
            "B-roll suggestions, and text overlay cues."
        ),
        enable_thinking=True,
        preferred_models=["emily-fast", "emily-reasoning"],
        temperature=0.8,
    ),
    "market_research": EmilySkill(
        name="Market Research",
        icon="\U0001f50d",
        description="Emily analyzes markets, competitors, and trends",
        system_addition=(
            "You are a market research analyst. Analyze competitor "
            "positioning, pricing strategies, ad creative patterns, and "
            "audience demographics. Identify gaps and opportunities. "
            "Use frameworks: Porter's Five Forces, SWOT, TAM/SAM/SOM. "
            "Provide actionable insights, not just data. Quantify "
            "market size and growth potential where possible."
        ),
        enable_web_search=True,
        enable_thinking=True,
        preferred_models=["emily-deep-think", "emily-reasoning", "o3"],
        temperature=0.3,
    ),
    "singing": EmilySkill(
        name="Singing & Music",
        icon="\U0001f3b5",
        description="Emily generates music, writes lyrics, and sings",
        system_addition=(
            "You can generate music and sing. When asked to sing or create "
            "music, write expressive lyrics with natural rhythm and flow. "
            "Structure songs with verse, chorus, bridge. Specify the style "
            "(pop, jazz, lo-fi, rock, R&B, etc.) and mood. When writing "
            "lyrics, focus on emotional resonance and singability — words "
            "that feel good to say out loud. You have access to MusicGen "
            "for instrumental generation and RVC for voice conversion."
        ),
        temperature=0.9,
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
            # Deserialise pipeline steps if present
            raw_pipeline = obj.pop("pipeline", [])
            steps = [PipelineStep(**s) for s in raw_pipeline] if raw_pipeline else []
            result[skill_id] = EmilySkill(**obj, pipeline=steps)
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
