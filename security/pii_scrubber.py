"""
PII scrubber for Emily's outgoing data streams.

Uses Microsoft Presidio (AnalyzerEngine + AnonymizerEngine) to detect and
redact personally-identifiable information before it is:
- Written to logs
- Stored in episodic/semantic memory
- Passed to external tools

Presidio supports 50+ entity types with regex, NER, checksum validators, and
context-aware scoring.  Falls back to regex-only mode if Presidio is not installed.

Scrubbing strategy: replace with <ENTITY_TYPE> placeholders.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)

# Regex fallback patterns (used when Presidio is unavailable)
_REGEX_PATTERNS: list[tuple[str, str]] = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<EMAIL_ADDRESS>"),
    (r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "<PHONE_NUMBER>"),
    (
        r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6011[0-9]{12})\b",
        "<CREDIT_CARD>",
    ),
    (r"\b\d{3}-\d{2}-\d{4}\b", "<US_SSN>"),
    (r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b", "<IP_ADDRESS>"),
]


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
    PII detection and redaction using Microsoft Presidio.

    Falls back to regex-only mode if Presidio is not installed.
    """

    def __init__(self, language: str = "en") -> None:
        self._language = language
        self._analyzer: object | None = None
        self._anonymizer: object | None = None
        self._presidio_available = False
        self._init_presidio()

    def _init_presidio(self) -> None:
        """Attempt to load Presidio engines."""
        try:
            from presidio_analyzer import AnalyzerEngine  # type: ignore[import-untyped]
            from presidio_anonymizer import AnonymizerEngine  # type: ignore[import-untyped]
            from presidio_anonymizer.entities import OperatorConfig  # type: ignore[import-untyped]

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            self._OperatorConfig = OperatorConfig
            self._presidio_available = True
            log.info("pii_scrubber_presidio_loaded")
        except ImportError:
            log.warning("presidio_not_installed_pii_regex_only")
        except Exception as exc:
            log.warning("presidio_init_failed", error=str(exc))

    def scrub(self, text: str) -> ScrubResult:
        """
        Scrub PII from a text string.

        Args:
            text: Input text potentially containing PII.

        Returns:
            ScrubResult with the cleaned text and found entities.
        """
        if self._presidio_available:
            return self._scrub_presidio(text)
        return self._scrub_regex(text)

    def _scrub_presidio(self, text: str) -> ScrubResult:
        """Scrub using Presidio's full NER + regex + checksum pipeline."""
        entities: list[dict[str, Any]] = []

        try:
            results = self._analyzer.analyze(  # type: ignore[union-attr]
                text=text,
                language=self._language,
                score_threshold=0.4,
            )

            if not results:
                return ScrubResult(original=text, scrubbed=text, entities_found=[])

            for r in results:
                entities.append(
                    {
                        "type": r.entity_type,
                        "start": r.start,
                        "end": r.end,
                        "score": round(r.score, 3),
                        "source": "presidio",
                    }
                )

            # Build operators: replace each entity type with <TYPE> placeholder
            operators = {}
            for r in results:
                if r.entity_type not in operators:
                    operators[r.entity_type] = self._OperatorConfig(
                        "replace", {"new_value": f"<{r.entity_type}>"}
                    )

            anonymized = self._anonymizer.anonymize(  # type: ignore[union-attr]
                text=text,
                analyzer_results=results,
                operators=operators,
            )
            scrubbed = anonymized.text

        except Exception as exc:
            log.error("presidio_scrub_error", error=str(exc))
            return self._scrub_regex(text)

        if text != scrubbed:
            log.debug("pii_scrubbed", entity_count=len(entities))

        return ScrubResult(original=text, scrubbed=scrubbed, entities_found=entities)

    def _scrub_regex(self, text: str) -> ScrubResult:
        """Fallback: regex-only scrubbing."""
        entities: list[dict[str, Any]] = []
        result = text

        for pattern, replacement in _REGEX_PATTERNS:
            matches = re.findall(pattern, result)
            if matches:
                for m in matches:
                    entities.append(
                        {
                            "type": replacement.strip("<>"),
                            "value": m,
                            "source": "regex",
                        }
                    )
                result = re.sub(pattern, replacement, result)

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
                    self.scrub_dict(item, fields)
                    if isinstance(item, dict)
                    else self.scrub(item).scrubbed
                    if isinstance(item, str)
                    else item
                    for item in v
                ]
            else:
                result[k] = v
        return result

    async def scrub_async(self, text: str) -> ScrubResult:
        """Async wrapper for scrub (Presidio NER is CPU-bound)."""
        import asyncio

        return await asyncio.to_thread(self.scrub, text)

    async def scrub_dict_async(
        self,
        data: dict[str, Any],
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Async wrapper for scrub_dict."""
        import asyncio

        return await asyncio.to_thread(self.scrub_dict, data, fields)

    def is_ner_available(self) -> bool:
        """Return True if Presidio NER is loaded and active."""
        return self._presidio_available
