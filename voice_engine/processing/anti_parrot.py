"""Voice-response anti-parroting safeguards for streamed LLM output."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

_TOKEN_RE = re.compile(r"[a-z0-9']+")
_MIRROR_LEADIN_RE = re.compile(
    r"^\s*(?:right|okay|well|so|yeah|alright|look)?\s*,?\s*"
    r"(?:you(?:'re| are)\s+(?:asking|saying|treating|talking about|"
    r"conflating|trying to|not (?:the first|wrong|just))|"
    r"you\s+(?:said|mean|just\s+said|didn'?t)|"
    r"what\s+(?:i\s+hear|you(?:'re| are)\s+(?:saying|asking))\s+(?:is|are)|"
    r"so\s+you(?:'re| are)\s+(?:saying|asking|not))\b[^.!?]*[.!?]?\s*",
    re.IGNORECASE,
)


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase lexical tokens."""
    return _TOKEN_RE.findall(text.lower())


def _token_overlap_ratio(a: str, b: str) -> float:
    """Return Jaccard overlap ratio between two token sets."""
    ta = set(_tokenize(a))
    tb = set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _remove_long_user_ngrams(text: str, user_text: str) -> str:
    """Remove longer exact token n-grams copied from the user utterance."""
    user_tokens = _tokenize(user_text)
    if len(user_tokens) < 4:
        return text

    cleaned = text
    max_window = min(7, len(user_tokens))
    for window in range(max_window, 3, -1):
        for idx in range(0, len(user_tokens) - window + 1):
            phrase = " ".join(user_tokens[idx : idx + window])
            if len(phrase) < 18:
                continue
            cleaned = re.sub(rf"\b{re.escape(phrase)}\b", "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", cleaned)
    return cleaned


def sanitize_voice_opening(text: str, user_text: str) -> str:
    """Sanitize opening text so it does not mirror user phrasing.

    Args:
        text: Opening fragment from the assistant response.
        user_text: Latest user utterance.

    Returns:
        Sanitized opening fragment.
    """
    cleaned = _MIRROR_LEADIN_RE.sub("", text).strip()
    if not cleaned:
        return ""

    first_sentence_match = re.match(r"^(.*?[.!?])(\s.*)?$", cleaned, flags=re.DOTALL)
    first_sentence = cleaned
    rest = ""
    if first_sentence_match:
        first_sentence = first_sentence_match.group(1).strip()
        rest = (first_sentence_match.group(2) or "").strip()

    overlap = _token_overlap_ratio(first_sentence, user_text)
    first_tokens = _tokenize(first_sentence)
    # Catch both long parrots (6+ tokens, 72% overlap) and short exact echoes
    is_long_parrot = overlap >= 0.72 and len(first_tokens) >= 6
    is_short_echo = overlap >= 0.90 and 0 < len(first_tokens) <= 5
    if is_long_parrot or is_short_echo:
        cleaned = rest
    else:
        cleaned = first_sentence + (f" {rest}" if rest else "")

    cleaned = _remove_long_user_ngrams(cleaned, user_text)
    return cleaned.strip()


def _opening_boundary(text: str, max_chars: int) -> int | None:
    """Return boundary index for opening sanitization, or None if not ready."""
    punctuation_match = re.search(r"[.!?]\s", text)
    if punctuation_match:
        return punctuation_match.end()
    if len(text) >= max_chars:
        return len(text)
    return None


async def filter_voice_parroting(
    token_stream: AsyncIterator[str],
    user_text: str,
) -> AsyncIterator[str]:
    """Filter streamed text to reduce mirrored/parroted voice output.

    This is a low-latency streaming filter: it sanitizes the opening segment
    (where parroting is most common) and then strips long copied n-grams from
    subsequent chunks.

    Args:
        token_stream: Raw assistant token stream.
        user_text: Latest user utterance.
    """
    if not user_text.strip():
        async for token in token_stream:
            yield token
        return

    opening_buffer = ""
    opening_done = False
    emitted_any = False

    async for token in token_stream:
        if not opening_done:
            opening_buffer += token
            boundary = _opening_boundary(opening_buffer, max_chars=220)
            if boundary is None:
                continue

            opening = opening_buffer[:boundary]
            remainder = opening_buffer[boundary:]
            opening_done = True
            opening_buffer = ""

            cleaned_opening = sanitize_voice_opening(opening, user_text)
            if cleaned_opening:
                emitted_any = True
                yield cleaned_opening

            if remainder:
                cleaned_remainder = _remove_long_user_ngrams(remainder, user_text).strip()
                if cleaned_remainder:
                    emitted_any = True
                    yield cleaned_remainder
            continue

        cleaned = _remove_long_user_ngrams(token, user_text)
        if cleaned:
            emitted_any = True
            yield cleaned

    if not opening_done and opening_buffer:
        cleaned_tail = sanitize_voice_opening(opening_buffer, user_text)
        if cleaned_tail:
            emitted_any = True
            yield cleaned_tail

    if not emitted_any:
        return
