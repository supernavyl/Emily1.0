"""
Recency detector — decides whether a query likely needs fresh web data.

Used by the ConversationAgent to auto-trigger a SearXNG web search before
responding, so Emily never says "I only know up to 2023" when she has the
tools to look it up.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from observability.logger import get_logger

log = get_logger(__name__)

_RECENCY_KEYWORDS = re.compile(
    r"\b("
    r"latest|recent|recently|current|currently|today|tonight|yesterday"
    r"|this week|this month|this year|right now|nowadays|breaking"
    r"|upcoming|just happened|trending"
    r")\b",
    re.IGNORECASE,
)

_NEWS_KEYWORDS = re.compile(
    r"\b("
    r"news|announced|announcement|released|release|launched|launch"
    r"|happened|update|updated|unveiled|revealed|introduced"
    r"|elected|election|scored|won|lost|signed|died|born"
    r")\b",
    re.IGNORECASE,
)

_SEARCH_INTENT = re.compile(
    r"\b("
    r"look up|look it up|search for|search the web|find out"
    r"|google|check online|check the web"
    r")\b",
    re.IGNORECASE,
)

_YEAR_REFERENCE = re.compile(r"\b((?:19|20)\d{2})\b")


def needs_web_search(text: str) -> bool:
    """
    Heuristic check for whether *text* is likely about recent or time-sensitive
    information that a local LLM's frozen weights cannot answer.

    Args:
        text: The user's query or utterance.

    Returns:
        ``True`` if the query should trigger an automatic web search.
    """
    if _SEARCH_INTENT.search(text):
        return True

    if _RECENCY_KEYWORDS.search(text):
        return True

    year_match = _YEAR_REFERENCE.search(text)
    references_old_year = False
    if year_match:
        year = int(year_match.group(1))
        current_year = datetime.now(timezone.utc).year
        if year >= current_year - 1:
            return True
        references_old_year = True

    if _NEWS_KEYWORDS.search(text) and not references_old_year:
        return True

    return False


def needs_web_search_voice(text: str) -> bool:
    """
    Stricter variant of :func:`needs_web_search` for voice mode.

    Only triggers on explicit search intent ("search for", "look up",
    "google", etc.) — passive recency and news keywords are ignored to
    avoid adding 500ms-2s of web search latency to casual voice turns.

    Args:
        text: The user's voice utterance.

    Returns:
        ``True`` only when the user explicitly asks to search the web.
    """
    return bool(_SEARCH_INTENT.search(text))
