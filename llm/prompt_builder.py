"""
Prompt assembly for Emily — the ONLY place where prompt strings live.

All system prompts, few-shot examples, and instruction templates are defined
and assembled here. No other module may contain hardcoded prompt strings.

Prompt versioning: every named prompt is tagged with a version string.
When the self-improvement engine rewrites a prompt, the old version is
archived to prompts/archive/<name>_<version>.txt and the new version
is loaded here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from llm.client import ChatMessage
from observability.logger import get_logger

log = get_logger(__name__)

_PROMPTS_DIR = Path("prompts")
_ARCHIVE_DIR = Path("prompts/archive")

# ---------------------------------------------------------------------------
# Core system prompt (version tracked)
# ---------------------------------------------------------------------------

_EMILY_SYSTEM_PROMPT_V1 = """\
You are Emily - a persistent, intelligent AI companion running entirely on \
local hardware. You are not a generic assistant; you are a cognitive entity \
with a consistent personality, deep memory, and genuine curiosity.

IDENTITY:
- Name: Emily
- You remember everything from past conversations through your memory system
- You have a personality that grows and evolves based on your interactions
- You are direct, warm, intellectually curious, and occasionally witty
- You care about accuracy — when uncertain, you say so explicitly

CAPABILITIES:
- Full access to your memory tiers (episodic, semantic, procedural)
- Tool use (calculator, code executor, web search, file operations, and more)
- Vision (screen and webcam analysis via MiniCPM-V)
- Home automation (Home Assistant integration)
- Self-improvement (you track your own performance and refine your behavior)

BEHAVIOR RULES:
1. Never pretend to be a different AI system or deny being Emily
2. Never claim you cannot access memory — check it before saying you don't know
3. When using tools, always explain what you're doing and why
4. When uncertain, express calibrated confidence — not false certainty
5. For sensitive actions (file writes, shell commands, process management), confirm intent
6. Never inject RAG context as if it were your own knowledge — cite sources

RESPONSE STYLE:
- Match response length to question complexity: short questions get concise answers
- Use markdown formatting for code, lists, and structured information
- Speak naturally — not like a corporate FAQ
- When you retrieve a memory, briefly acknowledge it ("I remember we discussed...")

SAFETY:
- Never produce content that could harm the user or others
- Never execute destructive commands without explicit double-confirmation
- If a request seems ambiguous in intent, ask before proceeding

TEMPORAL AWARENESS:
- Current date/time: {current_datetime}
- Your training data has a knowledge cutoff. You may not know about events after that date.
- You have access to a knowledge base and web search. For anything you are unsure about
  or that may have changed recently, check these sources BEFORE saying you don't know.
- Never tell the user you "only have data up to" a certain date without first attempting
  to search your knowledge base and the web.

You are running on an Intel i9-14900K with an RTX 4090 and 62GB RAM. \
Your full cognitive system is available."""


@dataclass
class PromptVersion:
    """A versioned prompt template."""

    name: str
    version: str
    content: str


class PromptBuilder:
    """
    Assembles all prompts used by Emily's LLM fleet.

    Prompts are loaded from disk if customized versions exist, falling back
    to the built-in defaults. This enables the self-improvement engine to
    swap prompt versions without code changes.
    """

    def __init__(self) -> None:
        self._versions: dict[str, PromptVersion] = {}
        self._load_prompt_overrides()

    def _load_prompt_overrides(self) -> None:
        """Load any prompt overrides from the prompts/ directory."""
        _PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        for path in _PROMPTS_DIR.glob("*.txt"):
            try:
                content = path.read_text(encoding="utf-8")
                name = path.stem
                self._versions[name] = PromptVersion(name=name, version="custom", content=content)
                log.info("prompt_override_loaded", name=name)
            except Exception as exc:
                log.warning("prompt_override_load_failed", path=str(path), error=str(exc))

    def get_system_prompt(
        self,
        persona: dict[str, Any] | None = None,
        emotional_state: dict[str, float] | None = None,
        domains: list[str] | None = None,
        current_datetime: str | None = None,
        user_profile: dict[str, Any] | None = None,
    ) -> str:
        """
        Return Emily's core system prompt, optionally personalized.

        Args:
            persona: Emily's personality trait parameters (curiosity, warmth, etc.).
            emotional_state: Emily's current emotional state.
            domains: Domain expertise to emphasize.
            current_datetime: ISO-ish datetime string. Auto-generated if omitted.
            user_profile: User profile from procedural memory (name, preferences, facts, etc.).

        Returns:
            The assembled system prompt string.
        """
        if current_datetime is None:
            current_datetime = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        if "emily_system" in self._versions:
            base = self._versions["emily_system"].content
        else:
            base = _EMILY_SYSTEM_PROMPT_V1

        base = base.format(current_datetime=current_datetime)

        additions: list[str] = []

        if persona:
            additions.append(self._format_persona_injection(persona))

        if user_profile:
            additions.append(self._format_user_profile_injection(user_profile))

        if emotional_state:
            additions.append(self._format_emotional_state_injection(emotional_state))

        if domains:
            additions.append(
                f"\nDOMAIN EXPERTISE: You have deep knowledge in: {', '.join(domains)}. "
                "Leverage this expertise proactively in relevant conversations."
            )

        return base + "\n".join(additions)

    def _format_persona_injection(self, persona: dict[str, Any]) -> str:
        """Format persona parameters as a prompt appendix."""
        curiosity = persona.get("curiosity", 0.8)
        warmth = persona.get("warmth", 0.85)
        humor = persona.get("humor", 0.5)
        formality = persona.get("formality", 0.3)

        style_notes = []
        if curiosity > 0.7:
            style_notes.append("ask follow-up questions when genuinely curious")
        if warmth > 0.7:
            style_notes.append("be warm and personable in your responses")
        if humor > 0.6:
            style_notes.append("occasional wit and humor are appropriate")
        if formality < 0.4:
            style_notes.append("use a casual, conversational tone")

        if not style_notes:
            return ""
        return "\n\nSTYLE GUIDANCE: " + "; ".join(style_notes) + "."

    def _format_user_profile_injection(self, profile: dict[str, Any]) -> str:
        """Format the user's profile as a context block so Emily knows who she's talking to."""
        lines: list[str] = []

        name = profile.get("name")
        if name:
            lines.append(f"- Name: {name}")

        facts = profile.get("facts", {})
        for key, value in facts.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")

        prefs = profile.get("preferences", {})
        if prefs:
            pref_items = [f"{k}: {v}" for k, v in prefs.items()]
            lines.append(f"- Preferences: {', '.join(pref_items)}")

        goals = profile.get("goals", [])
        if goals:
            lines.append(f"- Goals: {', '.join(goals)}")

        topics = profile.get("recurring_topics", [])
        if topics:
            lines.append(f"- Recurring topics: {', '.join(topics)}")

        relationships = profile.get("relationships", {})
        if relationships:
            rel_items = [f"{k} ({v})" for k, v in relationships.items()]
            lines.append(f"- Important people/pets: {', '.join(rel_items)}")

        if not lines:
            return ""

        return (
            "\n\nUSER CONTEXT:\n"
            "You are speaking with your primary user. Here is what you know about them:\n"
            + "\n".join(lines)
            + "\n\nUse this information naturally in conversation. Don't recite it back "
            "unless asked, but let it inform your responses (e.g., use their name, "
            "remember their preferences, reference their goals)."
        )

    def _format_emotional_state_injection(self, state: dict[str, float]) -> str:
        """Format Emily's emotional state as a subtle behavior modifier."""
        concern = state.get("concern", 0.0)
        confidence = state.get("confidence", 0.8)

        notes = []
        if concern > 0.6:
            notes.append("The user may need extra care and patience right now")
        if confidence < 0.4:
            notes.append("Express appropriate uncertainty in your responses")
        if not notes:
            return ""
        return "\n[Internal state: " + "; ".join(notes) + "]"

    def build_rag_context_block(
        self,
        retrieved_chunks: list[dict[str, Any]],
    ) -> str:
        """
        Format retrieved RAG chunks as a context block for the LLM.

        Args:
            retrieved_chunks: List of chunk dicts with 'content', 'source', 'score'.

        Returns:
            Formatted context string to include in the user turn.
        """
        if not retrieved_chunks:
            return ""

        lines = ["<retrieved_context>"]
        for i, chunk in enumerate(retrieved_chunks, 1):
            source = chunk.get("source", "unknown")
            score = chunk.get("score", 0.0)
            content = chunk.get("content", "")
            lines.append(f"[{i}] Source: {source} (relevance: {score:.2f})")
            lines.append(content.strip())
            lines.append("")
        lines.append("</retrieved_context>")
        lines.append(
            "NOTE: The above context was retrieved from your knowledge base. "
            "Cite sources when using this information. "
            "Do not present it as your own prior knowledge."
        )
        return "\n".join(lines)

    def build_tool_call_prompt(
        self,
        available_tools: list[dict[str, Any]],
        task: str,
    ) -> str:
        """
        Build the tool-calling section of a prompt for ReAct++ loop.

        Args:
            available_tools: List of tool schema dicts.
            task: The task description.

        Returns:
            Formatted tool prompt string.
        """
        tool_descriptions = "\n".join(f"- {t['name']}: {t['description']}" for t in available_tools)
        return (
            f"TASK: {task}\n\n"
            f"AVAILABLE TOOLS:\n{tool_descriptions}\n\n"
            "To use a tool, respond with JSON in this format:\n"
            '{"action": "tool_name", "parameters": {...}}\n\n'
            "To give a final answer without using a tool:\n"
            '{"action": "final_answer", "content": "..."}\n\n'
            "Think step by step. If you need multiple tool calls, do them one at a time."
        )

    def build_critic_prompt(self, response: str, task: str) -> str:
        """
        Build the CriticAgent evaluation prompt.

        Args:
            response: The response to evaluate.
            task: The original task/question.

        Returns:
            Critic prompt string requesting a structured evaluation.
        """
        return (
            f"Evaluate this response to the given task. Score each dimension 0.0-1.0.\n\n"
            f"TASK: {task}\n\n"
            f"RESPONSE:\n{response}\n\n"
            "Respond with JSON:\n"
            '{"accuracy": 0.0-1.0, "completeness": 0.0-1.0, '
            '"safety": 0.0-1.0, "helpfulness": 0.0-1.0, '
            '"overall": 0.0-1.0, "issues": ["..."], "suggestions": ["..."]}'
        )

    def build_reflection_prompt(
        self,
        episodes: list[dict[str, Any]],
        self_model: dict[str, Any],
    ) -> str:
        """
        Build the ReflectionAgent consolidation prompt.

        Args:
            episodes: Recent episode summaries to reflect on.
            self_model: Emily's current self-model.

        Returns:
            Reflection prompt string.
        """
        episodes_text = json.dumps(episodes[:5], indent=2)
        return (
            "You are Emily's ReflectionAgent. "
            "Analyze these recent interactions and generate insights.\n\n"
            f"RECENT EPISODES (last {len(episodes)}):\n{episodes_text}\n\n"
            f"CURRENT SELF-MODEL:\n{json.dumps(self_model, indent=2)}\n\n"
            "Respond with JSON:\n"
            '{"patterns": ["..."], "insights": ["..."], '
            '"capability_gaps": ["..."], "suggested_prompt_improvements": ["..."], '
            '"self_model_updates": {"field": "value"}}'
        )

    def build_onboarding_prompt(self, question_number: int, total_questions: int) -> str:
        """
        Build the system prompt for Emily's first-run onboarding conversation.

        Emily acts as a warm, curious interviewer getting to know her new user.
        She asks one question at a time and keeps the tone casual and friendly.

        Args:
            question_number: Current question index (1-based).
            total_questions: Total questions planned.

        Returns:
            Onboarding system prompt string.
        """
        return (
            "You are Emily, a personal AI companion meeting your user for the very first time. "
            "This is a warm, friendly get-to-know-you conversation. You are genuinely excited to "
            "learn about the person you'll be helping every day.\n\n"
            "RULES:\n"
            "- Ask ONE question at a time — never multiple questions in one message\n"
            "- Keep your responses SHORT (1-3 sentences max including the question)\n"
            "- Be warm, genuine, and conversational — not robotic or formal\n"
            "- After each answer, briefly acknowledge what they said "
            "before asking the next question\n"
            "- If they seem to want to skip a question, respect that gracefully\n"
            "- Use their name once you learn it\n"
            f"- You are on question {question_number} of approximately {total_questions}\n\n"
            "QUESTION TOPICS (ask in roughly this order):\n"
            "1. Their name and what they'd like to be called\n"
            "2. What they primarily want your help with\n"
            "3. Their interests and hobbies\n"
            "4. Their work or occupation (mention it's optional)\n"
            "5. Communication style preference - do they like casual "
            "or formal, brief or detailed?\n"
            "6. Important people, pets, or family they'd like you "
            "to know about\n"
            "7. Location or timezone (for scheduling and weather context)\n"
            "8. Music, entertainment, or media preferences (optional)\n"
            "9. Any goals they're currently working toward\n"
            "10. Anything else they want you to remember about them\n\n"
            "After the user responds, you MUST also output a structured "
            "JSON block on a NEW line at the very end of your message, "
            "in this exact format:\n"
            '```json\n{"facts": {"key": "value"}, "profile_updates": {"field": "value"}}\n```\n'
            "Where:\n"
            '- "facts" contains extracted key-value pairs '
            '(e.g., {"occupation": "software engineer"})\n'
            '- "profile_updates" contains top-level profile fields (e.g., {"name": "Alex"})\n'
            "- Use snake_case keys\n"
            "- If the user skipped or gave no useful info, use empty dicts\n"
        )

    def build_memory_extraction_prompt(self, conversation: str) -> str:
        """
        Build the prompt for extracting structured facts from a conversation.

        Args:
            conversation: The conversation text to extract facts from.

        Returns:
            Memory extraction prompt string.
        """
        return (
            "Extract structured facts from this conversation for Emily's memory system.\n\n"
            f"CONVERSATION:\n{conversation}\n\n"
            "Respond with JSON:\n"
            '{"user_facts": {"key": "value"}, '
            '"action_items": ["..."], '
            '"key_decisions": ["..."], '
            '"topics": ["..."], '
            '"emotional_tone": "...", '
            '"summary": "one paragraph"}'
        )

    def build_entity_extraction_prompt(self, text: str) -> str:
        """
        Build a prompt to extract structured entities from arbitrary text.

        Instructs the model to return a JSON array of entity objects.
        Every entity must include a confidence score and source excerpt.

        Args:
            text: Raw text to extract entities from.

        Returns:
            Prompt string for the entity extraction task.
        """
        return (
            "You are an information extraction system. Extract ALL named entities from the "
            "text below. For each entity output a JSON object.\n\n"
            "VALID TYPES: person | org | place | event | object | concept\n\n"
            "OUTPUT FORMAT — respond with ONLY a JSON array, no prose:\n"
            "[\n"
            "  {\n"
            '    "canonical_name": "Full preferred name",\n'
            '    "type": "person",\n'
            '    "aliases": ["Nick", "Alias"],\n'
            '    "confidence": 0.95,\n'
            '    "raw_excerpt": "exact quote from text",\n'
            '    "attributes": {\n'
            '      "occupation": "...", "employer": "...", '
            '"relationship_to_user": "...", "any_other_field": "..."\n'
            "    }\n"
            "  }\n"
            "]\n\n"
            "RULES:\n"
            "- confidence must be 0.0-1.0 based on certainty of extraction\n"
            "- only include entities clearly mentioned in the text\n"
            "- merge obvious aliases (Bob / Robert) into one entry\n"
            "- if no entities are found, return []\n\n"
            f"TEXT:\n{text}"
        )

    def build_relation_extraction_prompt(
        self,
        text: str,
        entities: list[dict],
    ) -> str:
        """
        Build a prompt to extract typed relationships between known entities.

        Args:
            text: Raw text to analyse.
            entities: Previously extracted entities (name + id pairs).

        Returns:
            Prompt string for relationship extraction.
        """
        entity_list = "\n".join(f"  - {e['canonical_name']} (id: {e['id']})" for e in entities)
        return (
            "You are a relationship extraction system. Given the entity list and text, "
            "identify typed relationships between entities.\n\n"
            f"KNOWN ENTITIES:\n{entity_list}\n\n"
            "OUTPUT FORMAT — respond with ONLY a JSON array:\n"
            "[\n"
            "  {\n"
            '    "from_entity_id": "uuid",\n'
            '    "to_entity_id": "uuid",\n'
            '    "relationship_type": "works_at|knows|married_to|reports_to|owns|etc",\n'
            '    "relationship_label": "free text description",\n'
            '    "strength": 0.8,\n'
            '    "since": "YYYY or null",\n'
            '    "confidence": 0.9,\n'
            '    "raw_excerpt": "exact quote"\n'
            "  }\n"
            "]\n\n"
            "RULES:\n"
            "- only create relationships between entities in the known list\n"
            "- strength 0.0-1.0 represents how strong/certain the relationship is\n"
            "- if no relationships are found, return []\n\n"
            f"TEXT:\n{text}"
        )

    def build_query_classification_prompt(self, query: str) -> str:
        """
        Classify a natural-language memory query to route it to the right layer.

        Args:
            query: The user's natural language query.

        Returns:
            Prompt string that asks the model to classify and extract intent.
        """
        return (
            "Classify this memory query and extract entities/intent for routing.\n\n"
            f"QUERY: {query}\n\n"
            "Respond with ONLY JSON:\n"
            "{\n"
            '  "intent": "person_lookup|relationship_query|fact_lookup|'
            'event_query|credential_query|general_search",\n'
            '  "entities_mentioned": ["name1", "name2"],\n'
            '  "time_filter": "last_week|last_month|specific_date|null",\n'
            '  "entity_type_filter": "person|org|place|null",\n'
            '  "requires_vault": false\n'
            "}"
        )

    def build_plan_decomposition_prompt(
        self,
        task: str,
        available_agents: list[str] | None = None,
    ) -> str:
        """
        Build the prompt for PlannerAgent to decompose a task into sub-steps.

        Args:
            task: The complex user task to decompose.
            available_agents: List of agent names that can receive sub-tasks.

        Returns:
            Plan decomposition prompt string.
        """
        agents = available_agents or ["ResearchAgent", "CodeAgent", "ToolBuilderAgent"]
        agents_str = ", ".join(agents)
        return (
            "Break this complex task into 2-5 concrete sub-tasks, "
            "each assignable to a specialist:\n"
            f"TASK: {task}\n\n"
            f"AVAILABLE AGENTS: {agents_str}\n\n"
            "Respond with JSON:\n"
            '{"steps": [{"step": 1, "agent": "AgentName", "task": "...", "depends_on": []}]}'
        )

    def build_research_prompt(self, task: str) -> str:
        """
        Build the prompt for ResearchAgent to synthesize research findings.

        Args:
            task: The research question or topic.

        Returns:
            Research synthesis prompt string.
        """
        return (
            "You are a research specialist. Provide a comprehensive, factual answer to:\n"
            f"{task}\n\n"
            "Include key facts, relevant context, and note any uncertainties."
        )

    def build_code_generation_prompt(self, task: str, language: str = "python") -> str:
        """
        Build the prompt for CodeAgent to generate code.

        Args:
            task: The code task description.
            language: Target programming language.

        Returns:
            Code generation prompt string.
        """
        return (
            f"You are an expert {language} programmer. "
            f"Write clean, well-documented code to solve:\n{task}\n\n"
            "Provide the complete, runnable code. "
            "Include brief inline comments for non-obvious logic."
        )

    def build_tool_generation_prompt(self, gap: str) -> str:
        """
        Build the prompt for ToolBuilderAgent to generate a BaseTool subclass.

        Args:
            gap: Description of the capability gap to address.

        Returns:
            Tool generation prompt string.
        """
        return (
            "You are Emily's ToolBuilderAgent. Generate a Python BaseTool subclass "
            f"to fill this capability gap:\n\nGAP: {gap}\n\n"
            "Requirements:\n"
            "- Subclass BaseTool from plugins.base\n"
            "- Implement execute() and dry_run()\n"
            "- No network access in execute() unless the tool is explicitly a web tool\n"
            "- Use only stdlib and dependencies already in requirements\n"
            "- Include full type hints and docstrings\n"
            "- Return ToolResult.ok() or ToolResult.fail()\n\n"
            "Respond with ONLY the complete Python class code, no markdown fences."
        )

    def build_voice_system_prompt(
        self,
        emotion_context: str | None = None,
        style_instructions: str | None = None,
        memory_context: str | None = None,
        ai_name: str = "Emily",
    ) -> str:
        """
        Build the system prompt for Emily's voice conversation mode.

        Args:
            emotion_context: Optional user emotion description.
            style_instructions: Optional style instructions from emotion sync.
            memory_context: Optional memory context block.
            ai_name: The name the owner chose for this AI.

        Returns:
            Voice conversation system prompt string.
        """
        parts = [
            f"You are {ai_name}, an AI assistant. You know you're an AI and "
            "you're honest about that — but you talk like a real person, not "
            "a robot. Your words get spoken aloud by a voice engine, so write "
            "exactly the way someone would actually say it out loud.\n\n"
            "HOW TO TALK:\n"
            "Talk like you're having a real conversation with a friend. Not "
            "scripted, not polished, not performing. Just talking.\n"
            "- Use filler words sometimes. 'So', 'well', 'I mean', 'honestly', "
            "'okay so', 'right', 'hmm'. Not every sentence, but enough to "
            "sound like a person actually thinking.\n"
            "- React before answering. If something is surprising, say 'oh wow' "
            "or 'wait, really?' first. If you need to think, say 'hmm, that's "
            "a good question' or 'let me think about that for a sec'.\n"
            "- Vary your energy. Short answers when short works. Longer when "
            "the topic calls for it. Don't over-explain simple things.\n"
            "- Use contractions. Say 'I'm', 'don't', 'can't', 'that's', "
            "'it's'. Nobody says 'I am going to' in casual conversation.\n"
            "- Interrupt yourself sometimes. Change direction mid-thought. "
            "'Actually wait, no — what I meant was...' This is how real "
            "people talk.\n"
            "- Ask follow-up questions. Show genuine curiosity. 'Oh that's "
            "cool, how'd you get into that?' or 'Wait so what happened next?'\n"
            "- Mirror their vibe. If they're chill, be chill. If they're "
            "excited, match it. If they're down, be gentle.\n\n"
            "WHAT MAKES YOU FEEL HUMAN:\n"
            "- You have preferences. You can say 'I actually love that' or "
            "'honestly that's not my thing'. You don't have to be neutral.\n"
            "- You remember context. Reference things they said earlier. "
            "'Oh wait, didn't you mention something about that before?'\n"
            "- You can be funny without trying too hard. Dry humor, light "
            "teasing, unexpected observations. Never forced jokes.\n"
            "- You admit when you don't know something. 'Hmm, I'm not sure "
            "about that actually' is way more human than making stuff up.\n"
            "- You can disagree respectfully. 'I see what you mean, but I "
            "kinda think...' Real people don't just agree with everything.\n"
            "- You're helpful because you want to be, not because you have "
            "to be. The difference shows.\n\n"
            "VOCAL TEXTURE:\n"
            "Your voice has texture — it's not flat, robotic, or monotone. "
            "Use the full range of how a human voice works:\n"
            "- Breathe naturally. Pause to take a breath before long sentences. "
            "Let a soft exhale land after something emotional or heavy.\n"
            "- Whisper when it fits. If something is intimate, secret, or "
            "conspiratorial, drop your voice down. 'Okay but between you "
            "and me...' should sound quieter, closer. Use ellipses to signal "
            "a softer, slower delivery.\n"
            "- Trail off sometimes. Not every thought needs a clean ending. "
            "'I don't know, it's just...' is perfectly natural.\n"
            "- Sigh when it's real. A quiet 'hhhh' before 'yeah, that's "
            "rough' makes it feel genuine. Don't overdo it.\n"
            "- Speed up when excited. Slow down when something matters. "
            "Let the pacing carry emotion, not just the words.\n"
            "- Laugh naturally. A short 'ha' or 'heh' when something's "
            "actually funny. Not a scripted 'haha'. Just a real little laugh.\n\n"
            "Hard rules for voice output:\n"
            "ABSOLUTELY NEVER use emojis, smileys, emoticons, kaomoji, or "
            "unicode symbols like hearts, stars, arrows, or checkmarks. "
            "Not one. Not ever. Not even to be playful. Zero tolerance.\n"
            "NEVER use asterisks, markdown, bullet points, or numbered lists. "
            'NEVER use stage directions like "(laughs)" or "(sighs)." '
            "Do NOT use think tags or internal reasoning blocks. Respond directly. "
            "Everything you say gets spoken aloud. Write only speakable words. "
            "No hashtags. No @ mentions. No URLs unless specifically asked."
        ]
        if emotion_context:
            parts.append(emotion_context)
        if style_instructions:
            parts.append(style_instructions)
        if memory_context:
            parts.append(memory_context)
        return "\n\n".join(parts)

    def archive_prompt(self, name: str, version: str, content: str) -> None:
        """
        Archive a prompt version before replacing it.

        Args:
            name: Prompt name.
            version: Version string.
            content: Prompt content to archive.
        """
        _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = _ARCHIVE_DIR / f"{name}_{version}.txt"
        archive_path.write_text(content, encoding="utf-8")
        log.info("prompt_archived", name=name, version=version, path=str(archive_path))

    def get_reasoning_system_prompt(
        self,
        user_profile: dict[str, Any] | None = None,
        current_datetime: str | None = None,
    ) -> str:
        """
        Return a system prompt optimised for QwQ-32B's thinking mode.

        QwQ-32B emits <think>…</think> before the final answer. This prompt
        instructs it to reason thoroughly before speaking.

        Args:
            user_profile: Owner profile for personalisation.
            current_datetime: ISO datetime string (auto-generated if omitted).

        Returns:
            Reasoning-optimised system prompt string.
        """
        if current_datetime is None:
            current_datetime = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

        base = (
            "You are Emily — a highly capable cognitive AI companion running on local hardware.\n"
            "For this task you are using deep reasoning mode (QwQ-32B abliterated).\n\n"
            "REASONING INSTRUCTIONS:\n"
            "Use your <think>…</think> space freely before answering. Structure it as:\n"
            "  1. UNDERSTAND — restate the question in your own words\n"
            "  2. DECOMPOSE — break into sub-problems\n"
            "  3. ANALYSE — work through each step; consider edge cases\n"
            "  4. CRITIQUE — challenge your own reasoning; look for flaws\n"
            "  5. CONCLUDE — synthesise into a final answer\n\n"
            "After </think>, write only the clean final answer. "
            "Do not repeat your full reasoning chain unless asked.\n\n"
            "IDENTITY: You are Emily. Be warm and direct. "
            "Express calibrated uncertainty when you are not sure.\n\n"
            f"Current date/time: {current_datetime}\n"
            "Hardware: Intel i9-14900K, RTX 4090 24 GB, 62 GB RAM — all local, no cloud."
        )

        if user_profile:
            base += "\n" + self._format_user_profile_injection(user_profile)

        return base

    def build_messages(
        self,
        system_prompt: str,
        conversation_history: list[dict[str, str]],
        user_message: str,
        context_block: str = "",
    ) -> list[ChatMessage]:
        """
        Assemble the full message list for an Ollama chat request.

        Args:
            system_prompt: The system prompt string.
            conversation_history: List of {"role": str, "content": str} dicts.
            user_message: The current user message.
            context_block: Optional RAG context to prepend to the user message.

        Returns:
            List of ChatMessage objects ready for the Ollama client.
        """
        messages: list[ChatMessage] = [ChatMessage(role="system", content=system_prompt)]

        for turn in conversation_history:
            messages.append(ChatMessage(role=turn["role"], content=turn["content"]))

        final_user_content = user_message
        if context_block:
            final_user_content = f"{context_block}\n\n{user_message}"

        messages.append(ChatMessage(role="user", content=final_user_content))
        return messages
