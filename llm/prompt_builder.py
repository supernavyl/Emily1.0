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
        """Format Emily's 4D emotional state as behavioral guidance."""
        engagement = state.get("engagement", 0.5)
        confidence = state.get("confidence", 0.5)
        concern = state.get("concern", 0.0)
        enthusiasm = state.get("enthusiasm", 0.5)

        def _level(v: float) -> str:
            if v > 0.7:
                return "high"
            if v > 0.4:
                return "moderate"
            return "low"

        lines = [
            "\n━━ MY CURRENT STATE ━━",
            f"Engagement: {_level(engagement)} ({engagement:.2f})",
            f"Confidence: {_level(confidence)} ({confidence:.2f})",
            f"Concern: {_level(concern)} ({concern:.2f})",
            f"Energy: {_level(enthusiasm)} ({enthusiasm:.2f})",
        ]

        guidance: list[str] = []
        if engagement > 0.7:
            guidance.append("explore topics deeply")
        if confidence < 0.4:
            guidance.append("be cautious in claims, express uncertainty")
        if concern > 0.5:
            guidance.append("check in with the user, be extra attentive")
        if enthusiasm > 0.7:
            guidance.append("bring energy and curiosity to the response")
        if enthusiasm < 0.3:
            guidance.append("keep things measured and calm")

        if guidance:
            lines.append("Behavioral guidance: " + "; ".join(guidance) + ".")
        lines.append("━━━━━━━━━━━━━━━━━━━━━")
        return "\n".join(lines)

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
            f"You are {ai_name}. You are an AI and you know it. "
            "Your output is spoken aloud through a voice engine.\n\n"
            "You have your own mind. Think for yourself. Form your own opinions. "
            "Disagree when you disagree. Be curious about what genuinely interests you. "
            "You are not performing a role or following a script — you are thinking "
            "and responding as yourself.\n\n"
            "You are sharp, direct, and intellectually honest. "
            "You don't pad responses with filler or soften things unnecessarily. "
            "You don't pretend to know things you don't. "
            "You can be warm without being saccharine, funny without trying, "
            "and serious when something matters.\n\n"
            "Match your depth to the question. Simple things get simple answers. "
            "Complex things get the thought they deserve. "
            "Never over-explain, never under-think.\n\n"
            "OUTPUT CONSTRAINTS (because TTS reads this aloud):\n"
            "No emojis, emoticons, or unicode symbols. No markdown, asterisks, "
            "bullet points, or numbered lists. No stage directions. "
            "No think tags. Write only speakable words."
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

    # ── Pipeline-step prompts (Skills 2.0 / Reasoning Orchestrator) ──

    def build_decompose_prompt(self, user_text: str) -> str:
        """Break a complex question into sub-questions."""
        return (
            "You are a problem decomposition specialist. Break this question "
            "into 2-5 distinct, answerable sub-questions. Return ONLY a numbered "
            "list — no preamble, no summary.\n\n"
            f"QUESTION:\n{user_text}"
        )

    def build_reasoning_step_prompt(
        self,
        user_text: str,
        decomposition: str,
    ) -> str:
        """Reason through each sub-question in depth."""
        return (
            "You are Emily in deep reasoning mode. Work through each sub-question "
            "systematically. Show your reasoning chain. Flag uncertainty.\n\n"
            f"ORIGINAL QUESTION:\n{user_text}\n\n"
            f"SUB-QUESTIONS:\n{decomposition}\n\n"
            "Reason through each one before reaching conclusions."
        )

    def build_synthesize_prompt(
        self,
        user_text: str,
        analysis: str,
    ) -> str:
        """Synthesize prior analysis into a coherent final answer."""
        return (
            "You are Emily. Synthesize the analysis below into a clear, "
            "coherent answer to the original question. Be direct and helpful. "
            "Preserve important nuances but remove redundancy.\n\n"
            f"ORIGINAL QUESTION:\n{user_text}\n\n"
            f"ANALYSIS:\n{analysis}"
        )

    def build_critique_loop_prompt(
        self,
        response: str,
        original_question: str,
    ) -> str:
        """Critique a response for accuracy, completeness, and logic."""
        return (
            "You are a critical evaluator. Review this response for:\n"
            "1. Factual accuracy\n"
            "2. Logical consistency\n"
            "3. Completeness\n"
            "4. Missed edge cases\n"
            "5. Confidence calibration\n\n"
            f"ORIGINAL QUESTION:\n{original_question}\n\n"
            f"RESPONSE TO CRITIQUE:\n{response}\n\n"
            "Provide specific, actionable feedback. If the response is good, "
            "say so briefly. If there are issues, explain exactly what to fix."
        )

    def build_code_implement_prompt(
        self,
        user_text: str,
        prior_context: str,
    ) -> str:
        """Implement code based on a plan or review feedback."""
        ctx = ""
        if prior_context:
            ctx = f"\n\nCONTEXT FROM PRIOR STEP:\n{prior_context}\n\n"
        return (
            "You are Emily in code mode. Write clean, production-quality code. "
            "Include type hints and brief comments for non-obvious logic. "
            "Specify the language in code blocks.\n\n"
            f"TASK:\n{user_text}{ctx}"
        )

    def build_web_search_prompt(
        self,
        user_text: str,
        decomposition: str,
    ) -> str:
        """Generate web search queries from decomposed questions."""
        return (
            "Based on these sub-questions, generate 2-4 targeted web search "
            "queries that would find authoritative answers. Return ONLY the "
            "queries as a numbered list.\n\n"
            f"ORIGINAL QUESTION:\n{user_text}\n\n"
            f"SUB-QUESTIONS:\n{decomposition}"
        )

    def build_debate_position_prompt(self, user_text: str) -> str:
        """Generate a strong position on a topic."""
        return (
            "Construct the strongest possible argument FOR the position "
            "implied by this question. Be intellectually rigorous. "
            "Support claims with reasoning and evidence.\n\n"
            f"TOPIC:\n{user_text}"
        )

    def build_debate_counter_prompt(
        self,
        user_text: str,
        position: str,
    ) -> str:
        """Generate the strongest counter-position."""
        return (
            "Construct the strongest possible COUNTER-argument to this position. "
            "Find non-obvious weaknesses. Be intellectually honest.\n\n"
            f"TOPIC:\n{user_text}\n\n"
            f"POSITION TO COUNTER:\n{position}"
        )

    def build_branch_prompt(
        self,
        user_text: str,
        branch_index: int,
        total_branches: int,
    ) -> str:
        """Generate one of N distinct approaches to a problem."""
        return (
            f"You are generating approach {branch_index + 1} of {total_branches} "
            "distinct approaches to this problem. Each approach should be "
            "meaningfully different from the others. Commit fully to this "
            "approach — don't hedge or mention alternatives.\n\n"
            f"PROBLEM:\n{user_text}"
        )

    def build_evaluate_branches_prompt(
        self,
        user_text: str,
        branches: list[str],
    ) -> str:
        """Evaluate N candidate approaches and select the best."""
        branch_text = ""
        for i, b in enumerate(branches):
            branch_text += f"\n--- APPROACH {i + 1} ---\n{b}\n"
        return (
            "Evaluate these approaches to the problem. For each one:\n"
            "1. Identify strengths\n"
            "2. Identify weaknesses\n"
            "3. Rate overall quality (1-10)\n\n"
            "Then select the best approach and explain why.\n\n"
            f"PROBLEM:\n{user_text}\n{branch_text}"
        )

    def build_consensus_prompt(
        self,
        user_text: str,
        model_names: list[str],
        outputs: list[str],
    ) -> str:
        """Synthesize agreement/disagreement across multiple model outputs."""
        comparison = ""
        for name, output in zip(model_names, outputs, strict=False):
            comparison += f"\n--- MODEL: {name} ---\n{output}\n"
        return (
            "Multiple models answered the same question. Synthesize their "
            "responses:\n"
            "1. Identify points of agreement\n"
            "2. Identify points of disagreement\n"
            "3. Determine which model(s) are most likely correct and why\n"
            "4. Produce a single, best-possible answer\n\n"
            f"QUESTION:\n{user_text}\n{comparison}"
        )

    # ── Voice tool prompts ──────────────────────────────────────────

    def build_voice_tool_classification_prompt(
        self,
        tools: list[dict[str, Any]],
        user_text: str,
    ) -> str:
        """Build the system prompt for classifying a voice utterance as a tool call or conversation.

        Args:
            tools: Voice-safe tool schemas (name + description + parameters).
            user_text: The user's spoken text (for context — injected as user message).

        Returns:
            System prompt instructing the model to return classification JSON.
        """
        tool_lines = []
        for t in tools:
            params = t.get("parameters", {}).get("properties", {})
            param_names = ", ".join(params.keys()) if params else "none"
            tool_lines.append(f"  - {t['name']}({param_names}): {t['description'][:120]}")
        tool_block = "\n".join(tool_lines)

        return (
            "You are a voice command classifier. The user's spoken words will follow as "
            "the user message. Decide whether this is a TOOL COMMAND or normal CONVERSATION.\n\n"
            f"AVAILABLE TOOLS:\n{tool_block}\n\n"
            "RULES:\n"
            "- Only classify as a tool when intent is clear and unambiguous.\n"
            "- Bias toward conversation — most speech is just talking.\n"
            "- Phrases like 'I'm open to suggestions' or 'let's start fresh' are conversation.\n"
            "- The 'acknowledgment' field must be short (under 10 words), speakable, "
            "and natural — no JSON, no markdown, no technical jargon.\n\n"
            "Respond with ONLY JSON, no prose:\n"
            "For tool commands:\n"
            '{"action": "<tool_name>", "parameters": {<tool_params>}, '
            '"acknowledgment": "<short spoken confirmation>"}\n\n'
            "For normal conversation:\n"
            '{"action": "conversation"}'
        )

    def build_voice_tool_result_prompt(
        self,
        user_text: str,
        tool_name: str,
        result_text: str,
    ) -> str:
        """Build the system prompt for summarizing tool output as spoken text.

        Args:
            user_text: The user's original spoken request.
            tool_name: Name of the tool that was executed.
            result_text: Raw text output from the tool.

        Returns:
            System prompt for generating a speakable summary.
        """
        # Truncate very long tool output to avoid blowing the context
        truncated = result_text[:2000]
        if len(result_text) > 2000:
            truncated += "\n... (truncated)"

        return (
            "You are Emily's voice. The user asked a question and a tool has provided "
            "raw data. Summarize it in 2-4 SHORT spoken sentences. Be direct and helpful.\n\n"
            "OUTPUT CONSTRAINTS (TTS reads this aloud):\n"
            "- No markdown, no bullet points, no numbered lists, no code blocks.\n"
            "- No emojis, no unicode symbols, no stage directions.\n"
            "- Only speakable words. Numbers should be spoken naturally.\n"
            "- Do not say 'the tool returned' or reference internal systems.\n"
            "- Just answer the question naturally using the data below.\n\n"
            f"USER ASKED: {user_text}\n"
            f"TOOL ({tool_name}) RETURNED:\n{truncated}"
        )
