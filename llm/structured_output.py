"""
Structured output enforcement for Emily.

Provides utilities to extract and validate JSON from LLM outputs.
Ollama supports grammar-constrained generation (GBNF) for guaranteed
JSON output, but we also handle regex-based extraction as fallback.
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from observability.logger import get_logger

log = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.MULTILINE)
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def extract_json(text: str) -> dict[str, Any] | None:
    """
    Extract the first JSON object from an LLM response.

    Tries multiple strategies:
    1. Parse the entire text as JSON
    2. Extract from a ```json...``` code block
    3. Find the first { ... } block via regex

    Args:
        text: LLM response text potentially containing JSON.

    Returns:
        Parsed dict, or None if no valid JSON found.
    """
    # Strategy 1: full parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: code block
    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Strategy 3: first {...} block
    match = _JSON_OBJECT_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    log.warning("json_extraction_failed", text_preview=text[:100])
    return None


def extract_and_validate(text: str, model: type[T]) -> T | None:
    """
    Extract JSON from LLM text and validate it against a Pydantic model.

    Args:
        text: LLM response text.
        model: Pydantic model class to validate against.

    Returns:
        Validated model instance, or None if extraction or validation fails.
    """
    raw = extract_json(text)
    if raw is None:
        return None
    try:
        return model(**raw)
    except (ValidationError, TypeError) as exc:
        log.warning("json_validation_failed", model=model.__name__, error=str(exc))
        return None


def require_json_response(text: str, required_keys: list[str]) -> dict[str, Any] | None:
    """
    Extract JSON and verify it contains all required keys.

    Args:
        text: LLM response text.
        required_keys: Keys that must be present in the parsed dict.

    Returns:
        Parsed dict if all keys present, else None.
    """
    raw = extract_json(text)
    if raw is None:
        return None
    missing = [k for k in required_keys if k not in raw]
    if missing:
        log.warning("json_missing_keys", missing=missing)
        return None
    return raw
