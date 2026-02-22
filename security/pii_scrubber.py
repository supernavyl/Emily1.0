"""
PII scrubber for Emily's outgoing data streams.

Uses spaCy NER (Named Entity Recognition) to detect and redact
personally-identifiable information before it is:
- Written to logs
- Stored in episodic/semantic memory
- Passed to external tools

Detected entity types:
- PERSON — full names
- EMAIL — email addresses (regex)
- PHONE_NUM — phone numbers (regex)
- GPE / LOC — geopolitical entities / locations
- ORG — organisations (optional, context-dependent)
- DATE — specific dates (when combined with other PII)
- CREDIT_CARD — credit card numbers (regex)

Scrubbing strategy: replace with <ENTITY_TYPE> placeholders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

# Regex patterns for entity types not reliably caught by NER
_REGEX_PATTERNS: list[tuple[str, str]] = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<EMAIL>"),
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "<PHONE>"),
    (r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6011[0-9]{12})\b", "<CREDIT_CARD>"),
    (r"\b\d{3}-\d{2}-\d{4}\b", "<SSN>"),  # US Social Security Number
    (r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "<IP_ADDRESS>"),
]

# NER label → replacement token
_NER_REPLACEMENTS: dict[str, str] = {
    "PERSON": "<PERSON>",
    "GPE": "<LOCATION>",
    "LOC": "<LOCATION>",
    "FAC": "<LOCATION>",
    "ORG": "<ORG>",
    "DATE": "<DATE>",
}


@dataclass
class ScrubResult:
    """Result of a PII scrubbing operation."""

    original: str
    scrubbed: str
    entities_found: list[dict[str, Any]]

    @property
    def was_modified(self) -> bool:
        return self.original != self.scrubbed


class PIIScrubber:
    """
    PII detection and redaction using spaCy NER + regex.

    Falls back to regex-only mode if spaCy or the English model is unavailable.
    """

    def __init__(self, spacy_model: str = "en_core_web_sm") -> None:
        """
        Args:
            spacy_model: spaCy model name for NER.
        """
        self._nlp: object | None = None
        self._ner_available = False
        self._spacy_model = spacy_model
        self._init_nlp()

    def _init_nlp(self) -> None:
        """Attempt to load the spaCy NER model."""
        try:
            import spacy
            try:
                self._nlp = spacy.load(self._spacy_model, exclude=["parser", "senter"])
                self._ner_available = True
                log.info("pii_scrubber_ner_loaded", model=self._spacy_model)
            except OSError:
                log.warning(
                    "spacy_model_not_found",
                    model=self._spacy_model,
                    hint=f"Run: python -m spacy download {self._spacy_model}",
                )
        except Exception:
            log.warning("spacy_not_installed_pii_regex_only")

    def scrub(self, text: str) -> ScrubResult:
        """
        Scrub PII from a text string.

        Args:
            text: Input text potentially containing PII.

        Returns:
            ScrubResult with the cleaned text and found entities.
        """
        entities: list[dict[str, Any]] = []
        result = text

        # 1. Regex-based scrubbing (fast, always runs)
        for pattern, replacement in _REGEX_PATTERNS:
            matches = re.findall(pattern, result)
            if matches:
                for m in matches:
                    entities.append({"type": replacement.strip("<>"), "value": m, "source": "regex"})
                result = re.sub(pattern, replacement, result)

        # 2. NER-based scrubbing
        if self._ner_available and self._nlp is not None:
            try:
                doc = self._nlp(result)  # type: ignore[call-arg]
                for ent in doc.ents:
                    label = ent.label_
                    if label in _NER_REPLACEMENTS:
                        token = _NER_REPLACEMENTS[label]
                        entities.append({
                            "type": label,
                            "value": ent.text,
                            "start": ent.start_char,
                            "end": ent.end_char,
                            "source": "ner",
                        })
                        result = result.replace(ent.text, token)
            except Exception as exc:
                log.error("ner_scrub_error", error=str(exc))

        if text != result:
            log.debug("pii_scrubbed", entity_count=len(entities))

        return ScrubResult(original=text, scrubbed=result, entities_found=entities)

    def scrub_dict(self, data: dict[str, Any], fields: list[str] | None = None) -> dict[str, Any]:
        """
        Scrub PII from string values in a dictionary, recursing into nested dicts and lists.

        Args:
            data: Dictionary to scrub.
            fields: Specific keys to scrub. If None, all string values are scrubbed.

        Returns:
            New dictionary with PII removed from the specified (or all) fields.
        """
        result: dict[str, Any] = {}
        for k, v in data.items():
            if fields and k not in fields:
                result[k] = v
            elif isinstance(v, str):
                result[k] = self.scrub(v).scrubbed
            elif isinstance(v, dict):
                result[k] = self.scrub_dict(v, fields)
            elif isinstance(v, list):
                result[k] = [
                    self.scrub_dict(item, fields) if isinstance(item, dict)
                    else self.scrub(item).scrubbed if isinstance(item, str)
                    else item
                    for item in v
                ]
            else:
                result[k] = v
        return result

    async def scrub_async(self, text: str) -> ScrubResult:
        """Async wrapper for scrub (spaCy NER is CPU-bound)."""
        import asyncio
        return await asyncio.to_thread(self.scrub, text)

    async def scrub_dict_async(
        self, data: dict[str, Any], fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Async wrapper for scrub_dict."""
        import asyncio
        return await asyncio.to_thread(self.scrub_dict, data, fields)

    def is_ner_available(self) -> bool:
        """Return True if spaCy NER is loaded and active."""
        return self._ner_available
