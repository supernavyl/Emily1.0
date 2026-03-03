"""
Enhanced Onboarding with Personal Questions and Confirmation.

This module runs a comprehensive first-run interview where Emily:
1. Asks who the owner is and sets up a verification passphrase
2. Asks personal questions to get to know the owner
3. CONFIRMS each answer before saving it
4. Stores all information securely

The owner is the ONLY person Emily fully trusts with personal data.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from llm.prompt_builder import PromptBuilder
from llm.router import ModelTier, TaskType
from observability.logger import get_logger
from users.owner_identity import OwnerIdentityManager

log = get_logger(__name__)


# Personal questions Emily asks during onboarding
# Each has: question, fact_key, confirmation_prompt
PERSONAL_QUESTIONS = [
    {
        "question": "First off, what's your name?",
        "fact_key": "name",
        "confirmation": "So your name is {answer}. Did I get that right?",
        "important": True,  # Must be confirmed
    },
    {
        "question": "What would you like to call me? My default name is Emily, but you can choose anything you like.",
        "fact_key": "ai_name",
        "confirmation": "So you'd like to call me {answer}. Is that right?",
        "important": True,
    },
    {
        "question": "Nice to meet you! Now, I'd like to set up a secret passphrase that only you and I will know. This way I can always verify it's really you. What would you like your passphrase to be? It can be a word, phrase, or sentence.",
        "fact_key": "passphrase",
        "confirmation": "I've got your passphrase. I won't repeat it out loud for security. Is that the one you want to use?",
        "important": True,
        "is_passphrase": True,  # Special handling
    },
    {
        "question": "What do you do for work, or what are you most passionate about?",
        "fact_key": "occupation",
        "confirmation": "So you're into {answer}. Is that correct?",
    },
    {
        "question": "What are some of your hobbies or things you enjoy doing in your free time?",
        "fact_key": "hobbies",
        "confirmation": "Great, so you enjoy {answer}. Did I understand that right?",
    },
    {
        "question": "Is there anything you're currently working on or learning that you'd like help with?",
        "fact_key": "current_projects",
        "confirmation": "Okay, so you're working on {answer}. Is that accurate?",
    },
    {
        "question": "What's your preferred communication style? Do you like detailed explanations or quick, concise answers?",
        "fact_key": "communication_style",
        "confirmation": "Got it, you prefer {answer}. Is that right?",
    },
    {
        "question": "Are there any topics you're particularly interested in or would like to explore together?",
        "fact_key": "interests",
        "confirmation": "So you're interested in {answer}. Correct?",
    },
    {
        "question": "Is there anything specific you'd like me to remember about you?",
        "fact_key": "special_notes",
        "confirmation": "I'll remember that {answer}. Is that what you meant?",
    },
    {
        "question": "Lastly, are there any topics you'd prefer to keep private - things I should never discuss with anyone else?",
        "fact_key": "private_topics",
        "confirmation": "Understood, I'll keep {answer} completely private. Is that right?",
    },
]


async def run_owner_onboarding(
    fleet: Any,
    memory: Any,
    identity_manager: OwnerIdentityManager,
    speak: Callable[[str], Awaitable[None]],
    listen: Callable[[], Awaitable[str]],
) -> bool:
    """
    Run the comprehensive owner onboarding process.

    This establishes:
    1. Who the owner is (name + passphrase)
    2. Personal facts about the owner
    3. Privacy preferences

    All answers are CONFIRMED before saving.

    Args:
        fleet: LLMFleet for generating responses.
        memory: MemoryManager for storing facts.
        identity_manager: OwnerIdentityManager for owner registration.
        speak: TTS callback.
        listen: STT callback.

    Returns:
        True if onboarding completed successfully.
    """
    PromptBuilder()
    collected_facts: dict[str, Any] = {}
    passphrase: str | None = None
    owner_name: str | None = None
    ai_name: str = "Emily"

    # --- Opening ---
    opening = (
        "Hello! I'm Emily, your personal AI companion. "
        "Before we begin, I need to get to know you a little bit. "
        "I'll ask you some questions and confirm your answers to make sure I understand correctly. "
        "This information will help me serve you better, and I promise to keep everything private. "
        "Ready to get started?"
    )
    await speak(opening)

    response = await listen()

    # Check for consent
    consent_check = await _check_consent(fleet, response)
    if not consent_check:
        await speak(
            "No problem! Whenever you're ready to set things up, just let me know. I'll be here."
        )
        return False

    await speak("Great! Let's begin.")

    # --- Ask each question with confirmation ---
    for _i, q_data in enumerate(PERSONAL_QUESTIONS):
        question = q_data["question"]
        fact_key = q_data["fact_key"]
        confirmation_template = q_data["confirmation"]
        q_data.get("important", False)
        is_passphrase = q_data.get("is_passphrase", False)

        # Ask the question
        await speak(question)
        answer = await listen()

        # Skip if no meaningful answer
        if not answer or len(answer.strip()) < 2:
            await speak("I didn't quite catch that. Let's move on and you can tell me later.")
            continue

        # Store passphrase separately (don't speak it back)
        if is_passphrase:
            passphrase = answer.strip()
            confirmation = confirmation_template
        else:
            # Create confirmation by filling in the answer
            confirmation = confirmation_template.format(answer=answer.strip())

        # Confirm with user
        await speak(confirmation)
        confirm_response = await listen()

        # Check if confirmed
        confirmed = await _check_confirmation(fleet, confirm_response)

        if confirmed:
            if is_passphrase:
                # Don't store passphrase in regular facts
                await speak("Perfect, I've securely stored your passphrase.")
            else:
                collected_facts[fact_key] = answer.strip()
                await speak("Got it!")

                # Store special facts
                if fact_key == "name":
                    owner_name = answer.strip()
                elif fact_key == "ai_name":
                    ai_name = answer.strip() or "Emily"
                elif fact_key == "private_topics":
                    # Mark these as sensitive
                    topics = [t.strip() for t in answer.split(",")]
                    collected_facts["sensitive_topics"] = topics
        else:
            # Ask for correction
            await speak("Let me try again. What should I remember instead?")
            corrected = await listen()

            if corrected and len(corrected.strip()) >= 2:
                if is_passphrase:
                    passphrase = corrected.strip()
                    await speak("Okay, I've updated your passphrase.")
                else:
                    collected_facts[fact_key] = corrected.strip()
                    await speak("Got it, I'll remember that instead.")

                    if fact_key == "name":
                        owner_name = corrected.strip()
                    elif fact_key == "ai_name":
                        ai_name = corrected.strip() or "Emily"

    # --- Validate we have the essentials ---
    if not owner_name:
        await speak("I didn't catch your name. What should I call you?")
        owner_name = await listen()
        if owner_name:
            collected_facts["name"] = owner_name.strip()

    if not passphrase:
        await speak(
            "I still need a secret passphrase to verify it's you. What would you like to use?"
        )
        passphrase = await listen()

    if not owner_name or not passphrase:
        await speak(
            "I need at least your name and a passphrase to get started. "
            "Let's try again later when you're ready."
        )
        return False

    # --- Register the owner ---
    success = await identity_manager.register_owner(
        name=owner_name.strip(),
        passphrase=passphrase.strip(),
        personal_facts=collected_facts,
    )

    if not success:
        await speak("Something went wrong setting up your profile. Let's try again later.")
        return False

    # --- Save AI name ---
    await identity_manager.update_ai_name(ai_name)

    # --- Save to procedural memory too ---
    for key, value in collected_facts.items():
        if key != "passphrase":  # Never store passphrase in regular memory
            await memory.procedural.set_user_fact(key, value)

    # --- Closing ---
    closing = (
        f"Wonderful, {owner_name}! I've got everything set up. "
        f"You can call me {ai_name} from now on. "
        "I'll always know it's you when you say your passphrase. "
        "I'll keep all your personal information completely private and never share it with anyone else. "
        "So, what would you like to talk about?"
    )
    await speak(closing)

    log.info(
        "owner_onboarding_complete",
        owner_name=owner_name,
        facts_count=len(collected_facts),
    )

    return True


async def verify_owner_identity(
    identity_manager: OwnerIdentityManager,
    speak: Callable[[str], Awaitable[None]],
    listen: Callable[[], Awaitable[str]],
) -> bool:
    """
    Verify that the current speaker is the owner.

    Args:
        identity_manager: OwnerIdentityManager instance.
        speak: TTS callback.
        listen: STT callback.

    Returns:
        True if speaker verified as owner.
    """
    if identity_manager.is_locked_out():
        await speak(
            "I'm sorry, but verification is temporarily locked due to too many failed attempts. "
            "Please try again in a few minutes."
        )
        return False

    await speak(
        f"Hi there! To make sure it's really you, {identity_manager.owner_name}, "
        "could you please say your secret passphrase?"
    )

    passphrase = await listen()

    if await identity_manager.verify_passphrase(passphrase.strip()):
        await speak(f"Welcome back, {identity_manager.owner_name}! It's great to hear from you.")
        return True
    else:
        remaining = (
            identity_manager._MAX_FAILED_ATTEMPTS
            - identity_manager._current_speaker.failed_attempts
        )
        if remaining > 0:
            await speak(
                f"Hmm, that doesn't match what I have. "
                f"You have {remaining} more attempts. Would you like to try again?"
            )
        else:
            await speak(
                "I'm sorry, but I'll need to lock verification for a few minutes for security. "
                "Please try again later."
            )
        return False


async def handle_guest_introduction(
    identity_manager: OwnerIdentityManager,
    speak: Callable[[str], Awaitable[None]],
    listen: Callable[[], Awaitable[str]],
) -> None:
    """
    Handle when a non-owner is detected or owner verification fails.

    Args:
        identity_manager: OwnerIdentityManager instance.
        speak: TTS callback.
        listen: STT callback.
    """
    identity_manager.mark_as_guest()

    await speak(
        "Hello! I'm Emily. I don't think we've verified who you are yet. "
        f"I primarily work with {identity_manager.owner_name}, but I'm happy to chat about general topics. "
        "Just so you know, I can't share any personal information without verification. "
        "How can I help you today?"
    )


def _word_match(word: str, text: str) -> bool:
    """Match whole words only using word boundaries."""
    return bool(re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE))


async def _check_consent(fleet: Any, response: str) -> bool:
    """Check if user consented to proceed."""
    response_lower = response.lower()

    # Quick heuristic check — negatives first to avoid false positives
    negative_words = ["no", "nope", "not", "don't", "later", "wait"]
    positive_words = ["yes", "yeah", "sure", "okay", "ok", "ready", "let's", "go", "yep", "yup"]

    if any(_word_match(word, response_lower) for word in negative_words):
        return False
    if any(_word_match(word, response_lower) for word in positive_words):
        return True

    # Use LLM for ambiguous cases
    result = await fleet.chat(
        user_message=f"The user said: '{response}'. Are they agreeing to proceed? Answer only 'yes' or 'no'.",
        messages=[],
        task_type=TaskType.CHAT,
        force_tier=ModelTier.NANO,
        max_tokens=10,
    )
    return "yes" in result.content.lower()


async def _check_confirmation(fleet: Any, response: str) -> bool:
    """Check if user confirmed the information."""
    response_lower = response.lower()

    # Quick heuristic check — negatives first to avoid false positives
    negative_words = ["no", "nope", "wrong", "incorrect", "not", "actually"]
    positive_words = [
        "yes",
        "yeah",
        "correct",
        "right",
        "yep",
        "yup",
        "that's right",
        "exactly",
        "perfect",
    ]

    if any(_word_match(word, response_lower) for word in negative_words):
        return False
    if any(_word_match(word, response_lower) for word in positive_words):
        return True

    # Use LLM for ambiguous cases
    result = await fleet.chat(
        user_message=f"The user said: '{response}'. Are they confirming something is correct? Answer only 'yes' or 'no'.",
        messages=[],
        task_type=TaskType.CHAT,
        force_tier=ModelTier.NANO,
        max_tokens=10,
    )
    return "yes" in result.content.lower()
