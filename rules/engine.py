"""Structured rules engine for Emily's execution pipeline.

Rules act as execution guards — not just prompt strings.  Each rule has a
scope, trigger point, condition, action, and priority.  The :class:`RulesEngine`
singleton manages built-in + custom rules and provides ordered lookup.

Trigger points:
- ``pre_response``  — evaluated before LLM generation starts
- ``post_response`` — evaluated after LLM generation completes
- ``pre_tool``      — evaluated before a tool call executes
- ``always``        — evaluated at every trigger point

Actions:
- ``inject_prompt``    — prepend/append text to the system prompt
- ``block``            — prevent the action and return a canned message
- ``modify_tier``      — force a different model tier
- ``require_approval`` — flag for user confirmation
- ``log``              — emit an observability event
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from observability.logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Rule:
    """A single execution guard rule."""

    id: str
    name: str
    scope: str = "global"
    trigger: str = "always"
    condition: str = ""
    action: str = "log"
    payload: str = ""
    priority: int = 50
    enabled: bool = True


# ── Singleton ─────────────────────────────────────────────────────

_engine: RulesEngine | None = None
_lock = threading.Lock()


def get_rules_engine() -> RulesEngine:
    """Return (and lazily create) the global RulesEngine singleton."""
    global _engine
    if _engine is None:
        with _lock:
            if _engine is None:
                _engine = RulesEngine()
    return _engine


class RulesEngine:
    """Central registry for execution rules.

    Built-in rules are immutable; custom rules persist to
    ``~/.emily-chat/custom_rules.json``.
    """

    _CUSTOM_PATH = Path.home() / ".emily-chat" / "custom_rules.json"

    def __init__(self, custom_path: Path | None = None) -> None:
        self._custom_path = custom_path or self._CUSTOM_PATH
        self._builtin: dict[str, Rule] = _builtin_rules()
        self._custom: dict[str, Rule] = self._load_custom()
        log.info(
            "rules_engine_init",
            builtin=len(self._builtin),
            custom=len(self._custom),
        )

    # ── Public API ────────────────────────────────────────────────

    def get(self, rule_id: str) -> Rule | None:
        return self._builtin.get(rule_id) or self._custom.get(rule_id)

    def list_all(self) -> dict[str, Rule]:
        merged = dict(self._custom)
        merged.update(self._builtin)
        return merged

    def create_custom(self, rule: Rule) -> None:
        if rule.id in self._builtin:
            raise ValueError(f"Cannot override built-in rule '{rule.id}'")
        self._custom[rule.id] = rule
        self._save_custom()

    def update_custom(self, rule_id: str, updates: dict[str, Any]) -> Rule:
        existing = self._custom.get(rule_id)
        if existing is None:
            raise KeyError(f"Custom rule '{rule_id}' not found")
        data = asdict(existing)
        data.update(updates)
        data["id"] = rule_id  # prevent ID mutation
        updated = Rule(**data)
        self._custom[rule_id] = updated
        self._save_custom()
        return updated

    def delete_custom(self, rule_id: str) -> bool:
        if rule_id not in self._custom:
            return False
        del self._custom[rule_id]
        self._save_custom()
        return True

    def is_builtin(self, rule_id: str) -> bool:
        return rule_id in self._builtin

    # ── Persistence ───────────────────────────────────────────────

    def _load_custom(self) -> dict[str, Rule]:
        if not self._custom_path.exists():
            return {}
        try:
            data = json.loads(self._custom_path.read_text("utf-8"))
            return {rid: Rule(**obj) for rid, obj in data.items()}
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            log.warning("custom_rules_load_failed", error=str(exc))
            return {}

    def _save_custom(self) -> None:
        self._custom_path.parent.mkdir(parents=True, exist_ok=True)
        data = {rid: asdict(r) for rid, r in self._custom.items()}
        self._custom_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def rule_to_dict(rule: Rule) -> dict[str, Any]:
        return asdict(rule)


# ── Built-in rule definitions ────────────────────────────────────


def _builtin_rules() -> dict[str, Rule]:
    return {
        "safety_gate": Rule(
            id="safety_gate",
            name="Safety Gate",
            scope="global",
            trigger="pre_response",
            condition=r"(?i)\b(how to (make|build) (a )?(bomb|weapon|drug)|synthesize (meth|fentanyl))\b",
            action="block",
            payload="I can't help with that request.",
            priority=0,
            enabled=True,
        ),
        "privacy_local_only": Rule(
            id="privacy_local_only",
            name="Privacy: Local Only",
            scope="global",
            trigger="pre_response",
            condition=r"(?i)\b(my (password|ssn|social security|credit card|bank account))\b",
            action="modify_tier",
            payload="smart",  # force local tier
            priority=10,
            enabled=True,
        ),
        "cloud_budget_limit": Rule(
            id="cloud_budget_limit",
            name="Cloud Budget Limit",
            scope="global",
            trigger="pre_response",
            condition="cloud_budget_exceeded",
            action="modify_tier",
            payload="reasoning",  # fall back to local reasoning
            priority=15,
            enabled=True,
        ),
        "voice_brevity": Rule(
            id="voice_brevity",
            name="Voice Brevity",
            scope="mode:voice",
            trigger="always",
            action="inject_prompt",
            payload="Keep responses under 3 sentences. Speak naturally and concisely.",
            priority=30,
            enabled=True,
        ),
        "code_security_review": Rule(
            id="code_security_review",
            name="Code Security Review",
            scope="skill:code",
            trigger="post_response",
            condition="contains_code_block",
            action="inject_prompt",
            payload="Review the generated code for security vulnerabilities (injection, XSS, SSRF, path traversal). Flag any issues.",
            priority=40,
            enabled=True,
        ),
        "research_citation": Rule(
            id="research_citation",
            name="Research Citation",
            scope="skill:research",
            trigger="always",
            action="inject_prompt",
            payload="Cite all factual claims with inline [1][2] markers. Include a sources list at the end.",
            priority=35,
            enabled=True,
        ),
    }
