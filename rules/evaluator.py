"""Rule evaluator — resolves applicable rules for the current context.

Given a trigger point, active mode, active skill, and user text, the evaluator
returns an ordered list of :class:`RuleAction` objects describing what the
pipeline should do (inject prompts, block, switch tiers, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from observability.logger import get_logger
from rules.engine import Rule, get_rules_engine

log = get_logger(__name__)


@dataclass
class RuleAction:
    """Resolved action to apply in the pipeline."""

    rule_id: str
    action: str  # inject_prompt | block | modify_tier | require_approval | log
    payload: str
    priority: int


class RuleEvaluator:
    """Stateless evaluator — call :meth:`evaluate` at each trigger point."""

    def evaluate(
        self,
        trigger: str,
        *,
        mode_id: str = "normal",
        skill_id: str = "normal",
        user_text: str = "",
        response_text: str = "",
        context: dict | None = None,
    ) -> list[RuleAction]:
        """Return ordered list of actions for the current context.

        Args:
            trigger: ``"pre_response"`` | ``"post_response"`` | ``"pre_tool"`` | ``"always"``
            mode_id: Active mode name.
            skill_id: Active skill name.
            user_text: The user's input (for condition matching).
            response_text: The model's output (for post_response conditions).
            context: Extra context dict (e.g. ``{"cloud_budget_exceeded": True}``).

        Returns:
            List of :class:`RuleAction` sorted by priority (lowest = highest priority).
        """
        ctx = context or {}
        engine = get_rules_engine()
        all_rules = engine.list_all()
        actions: list[RuleAction] = []

        for rule in all_rules.values():
            if not rule.enabled:
                continue
            if not self._trigger_matches(rule.trigger, trigger):
                continue
            if not self._scope_matches(rule.scope, mode_id, skill_id):
                continue
            if not self._condition_matches(rule, user_text, response_text, ctx):
                continue

            actions.append(
                RuleAction(
                    rule_id=rule.id,
                    action=rule.action,
                    payload=rule.payload,
                    priority=rule.priority,
                )
            )

        actions.sort(key=lambda a: a.priority)

        if actions:
            log.debug(
                "rules_evaluated",
                trigger=trigger,
                mode=mode_id,
                skill=skill_id,
                matched=[a.rule_id for a in actions],
            )

        return actions

    # ── Internal matchers ─────────────────────────────────────────

    @staticmethod
    def _trigger_matches(rule_trigger: str, current_trigger: str) -> bool:
        if rule_trigger == "always":
            return True
        return rule_trigger == current_trigger

    @staticmethod
    def _scope_matches(scope: str, mode_id: str, skill_id: str) -> bool:
        if scope == "global":
            return True
        if scope.startswith("mode:"):
            return scope.split(":", 1)[1] == mode_id
        if scope.startswith("skill:"):
            return scope.split(":", 1)[1] == skill_id
        return False

    @staticmethod
    def _condition_matches(
        rule: Rule,
        user_text: str,
        response_text: str,
        context: dict,
    ) -> bool:
        condition = rule.condition
        if not condition:
            return True  # no condition = always matches

        # Named context checks
        if condition == "cloud_budget_exceeded":
            return bool(context.get("cloud_budget_exceeded"))
        if condition == "contains_code_block":
            return "```" in response_text

        # Regex match against user text (pre_response) or response (post_response)
        text = response_text if rule.trigger == "post_response" else user_text
        try:
            return bool(re.search(condition, text))
        except re.error:
            log.warning("rule_condition_regex_error", rule=rule.id, condition=condition)
            return False
