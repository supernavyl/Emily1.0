"""
OnboardingAgent — first-run user profile interview.

Runs a multi-turn conversation where Emily asks the user about themselves
and saves all extracted facts to procedural memory. This only runs once,
on the very first startup when no user name is set.
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable

from llm.client import ChatMessage
from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier, TaskType
from observability.logger import get_logger

log = get_logger(__name__)

_TOTAL_QUESTIONS = 10


async def run_onboarding(
    fleet: Any,
    memory: Any,
    speak: Callable[[str], Awaitable[None]],
    listen: Callable[[], Awaitable[str]],
) -> None:
    """
    Drive a multi-turn onboarding interview via TTS/STT callbacks.

    After the conversation, all extracted facts are persisted to procedural memory
    so Emily always knows who she's talking to.

    Args:
        fleet: LLMFleet instance for generating Emily's questions.
        speak: Async callback that plays text via TTS and waits for playback.
        listen: Async callback that records and returns the user's spoken answer.
        memory: MemoryManager (must have .procedural with set_user_fact/update_user_profile).
    """
    prompts = PromptBuilder()
    conversation_history: list[ChatMessage] = []

    opening = (
        "Hi there! I'm Emily — your personal AI companion. "
        "I'd love to get to know you a little so I can be more helpful. "
        "Mind if I ask you a few questions?"
    )
    await speak(opening)
    conversation_history.append(ChatMessage(role="assistant", content=opening))

    answer = await listen()
    conversation_history.append(ChatMessage(role="user", content=answer))

    for q_num in range(1, _TOTAL_QUESTIONS + 1):
        system_prompt = prompts.build_onboarding_prompt(q_num, _TOTAL_QUESTIONS)

        messages = [ChatMessage(role="system", content=system_prompt)]
        messages.extend(conversation_history)

        result = await fleet.chat(
            user_message=answer,
            messages=messages,
            task_type=TaskType.CHAT,
            force_tier=ModelTier.VOICE_FAST,
            temperature=0.7,
            max_tokens=300,
        )

        emily_text = result.content.strip()

        facts_json = _extract_json_block(emily_text)
        display_text = _strip_json_block(emily_text)

        if facts_json:
            await _save_extracted_facts(memory, facts_json)

        if not display_text.strip():
            display_text = emily_text

        await speak(display_text)
        conversation_history.append(ChatMessage(role="assistant", content=emily_text))

        if q_num == _TOTAL_QUESTIONS:
            break

        answer = await listen()
        conversation_history.append(ChatMessage(role="user", content=answer))

    user_name = memory.procedural.get_user_fact("name") or "friend"
    closing = (
        f"Great getting to know you, {user_name}! "
        "I'll remember everything you've told me. "
        "You can always tell me more or update anything — just say the word. "
        "So, what can I help you with?"
    )
    await speak(closing)

    log.info(
        "onboarding_complete",
        user_name=user_name,
        facts_count=len(memory.procedural.user_profile.get("facts", {})),
    )


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Pull the ```json ... ``` block from Emily's response, if present."""
    pattern = r"```json\s*\n?(.*?)\n?\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        log.debug("onboarding_json_parse_failed", raw=match.group(1)[:200])
        return None


def _strip_json_block(text: str) -> str:
    """Remove the ```json ... ``` block so TTS doesn't read it aloud."""
    return re.sub(r"```json\s*\n?.*?\n?\s*```", "", text, flags=re.DOTALL).strip()


async def _save_extracted_facts(memory: Any, data: dict[str, Any]) -> None:
    """Persist facts and profile updates from a single onboarding turn."""
    facts = data.get("facts", {})
    for key, value in facts.items():
        if value:
            await memory.procedural.set_user_fact(key, value)

    profile_updates = data.get("profile_updates", {})
    if profile_updates:
        await memory.procedural.update_user_profile(profile_updates)
