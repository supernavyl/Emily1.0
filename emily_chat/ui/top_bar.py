"""Conversation top bar — model selector, skill picker, live stats, options.

Provides per-conversation controls that update live during streaming:
model/skill dropdowns, token/cost/context stats, cost and context
warning banners, and an options overflow menu.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QWidget,
)

from emily_chat.emily.skills import EMILY_SKILLS
from emily_chat.models.registry import (
    EMILY_MODEL_REGISTRY,
    ModelSpec,
    get_models_for_provider,
)

_COST_WARN_YELLOW = 0.05
_COST_WARN_RED = 0.20
_CTX_WARN_YELLOW = 75
_CTX_WARN_RED = 90

_MODEL_CATEGORIES: list[tuple[str, list[str]]] = [
    (
        "\U0001f9e0 EMILY (LOCAL BRAIN)",
        [
            "emily-fast",
            "emily-think",
            "emily-nano",
            "emily-vision",
        ],
    ),
    (
        "\U0001f9e0 THINKING MODELS",
        [
            "o3",
            "o4-mini",
            "gemini-3-pro",
            "gemini-3-flash",
            "gemini-2-5-pro",
            "groq-deepseek-r1",
            "deepseek-r2",
            "qwen3-72b",
            "kimi-k2-thinking",
            "glm-4-7-thinking",
        ],
    ),
    (
        "\u2696\ufe0f BALANCED",
        [
            "gpt-5-2",
            "gpt-5",
            "gpt-4o",
            "grok-4-1",
            "qwen3-235b",
        ],
    ),
    (
        "\u26a1 FAST",
        [
            "groq-llama-70b",
            "mistral-small-3",
        ],
    ),
    (
        "\U0001f4bb CODE SPECIALIST",
        [
            "codestral-2",
            "deepseek-v3-2",
        ],
    ),
    (
        "\U0001f310 MASSIVE CONTEXT",
        [
            "llama-4-scout",
            "llama-4-maverick",
        ],
    ),
    (
        "\U0001f1ea\U0001f1fa EU / PRIVACY",
        [
            "mistral-large-3",
        ],
    ),
    (
        "\U0001f193 FREE (CLOUD)",
        [
            "or-free-deepseek-r1",
            "or-free-qwen3-235b",
            "or-free-llama-70b",
            "or-free-gpt-oss-120b",
            "or-free-qwen3-vl-235b",
        ],
    ),
]


def group_models() -> list[tuple[str, list[tuple[str, ModelSpec]]]]:
    """Group registry models into display categories.

    Returns:
        List of ``(category_label, [(key, spec), ...])``.
    """
    result: list[tuple[str, list[tuple[str, ModelSpec]]]] = []
    seen: set[str] = set()
    for label, keys in _MODEL_CATEGORIES:
        items: list[tuple[str, ModelSpec]] = []
        for k in keys:
            spec = EMILY_MODEL_REGISTRY.get(k)
            if spec is not None:
                items.append((k, spec))
                seen.add(k)
        if items:
            result.append((label, items))
    # LOCAL (TabbyAPI): ExLlamaV2 abliterated models
    tabbyapi_models = {
        k: v for k, v in get_models_for_provider("tabbyapi").items() if k not in seen
    }
    if tabbyapi_models:
        items_tabbyapi = sorted(
            tabbyapi_models.items(),
            key=lambda p: (p[1].display, p[0]),
        )
        result.append(("\U0001f3e0 LOCAL (TabbyAPI)", items_tabbyapi))
        seen.update(tabbyapi_models.keys())
    # LOCAL (Ollama): vision + embedding models
    ollama_models = {k: v for k, v in get_models_for_provider("ollama").items() if k not in seen}
    if ollama_models:
        items_ollama = sorted(
            ollama_models.items(),
            key=lambda p: (p[1].display, p[0]),
        )
        result.append(("\U0001f3e0 LOCAL (Ollama)", items_ollama))
        seen.update(ollama_models.keys())
    # LOCAL (LlamaCpp / GGUF): nano + voice_fast in-process models
    llamacpp_models = {
        k: v for k, v in get_models_for_provider("llamacpp").items() if k not in seen
    }
    if llamacpp_models:
        items_llamacpp = sorted(
            llamacpp_models.items(),
            key=lambda p: (p[1].display, p[0]),
        )
        result.append(("\U0001f3e0 LOCAL (LlamaCpp)", items_llamacpp))
        seen.update(llamacpp_models.keys())
    leftover = [(k, v) for k, v in EMILY_MODEL_REGISTRY.items() if k not in seen]
    if leftover:
        result.append(("OTHER", leftover))
    return result


def format_cost(usd: float) -> str:
    """Format a USD cost value for display.

    Args:
        usd: Cost in USD.

    Returns:
        Formatted string like ``"$0.0124"`` or ``"$0.00"``.
    """
    if usd < 0.001:
        return "$0.00"
    return f"${usd:.4f}"


def format_tokens(n: int) -> str:
    """Format a token count with comma separators.

    Args:
        n: Token count.

    Returns:
        Formatted string like ``"4,247"``.
    """
    return f"{n:,}"


def cost_warning_level(usd: float) -> str:
    """Return the warning level for a cost value.

    Args:
        usd: Cost in USD.

    Returns:
        ``"red"``, ``"yellow"``, or ``"none"``.
    """
    if usd >= _COST_WARN_RED:
        return "red"
    if usd >= _COST_WARN_YELLOW:
        return "yellow"
    return "none"


def context_warning_level(pct: float) -> str:
    """Return the warning level for a context usage percentage.

    Args:
        pct: Context usage as a percentage (0-100).

    Returns:
        ``"red"``, ``"yellow"``, or ``"none"``.
    """
    if pct >= _CTX_WARN_RED:
        return "red"
    if pct >= _CTX_WARN_YELLOW:
        return "yellow"
    return "none"


class ConversationTopBar(QWidget):
    """Per-conversation controls with model selector, skill picker, and live stats.

    Signals:
        model_changed(str): Emitted when user selects a different model.
        skill_changed(str): Emitted when user selects a different skill.
        clear_requested(): Emitted from the options menu.
        fork_requested(): Emitted from the options menu.
        export_requested(str): Emitted with format string.
        system_prompt_edit_requested(): Emitted from the options menu.
    """

    model_changed = Signal(str)
    skill_changed = Signal(str)
    clear_requested = Signal()
    fork_requested = Signal()
    export_requested = Signal(str)
    system_prompt_edit_requested = Signal()
    emily_editor_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        self._model_btn = QPushButton("Emily \u2014 Auto \u25be")
        self._model_btn.setObjectName("modelSelectorBtn")
        self._model_btn.clicked.connect(self._show_model_menu)
        layout.addWidget(self._model_btn)

        self._skill_btn = QPushButton("\U0001f9e0 Normal \u25be")
        self._skill_btn.setObjectName("skillSelectorBtn")
        self._skill_btn.clicked.connect(self._show_skill_menu)
        layout.addWidget(self._skill_btn)

        layout.addStretch()

        self._stats_bar = QWidget()
        self._stats_bar.setObjectName("liveStatsBar")
        stats_layout = QHBoxLayout(self._stats_bar)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(12)

        self._stat_labels: dict[str, QLabel] = {}
        _stat_keys = (
            "tokens_in",
            "tokens_out",
            "tokens_think",
            "cost",
            "context",
            "time",
            "first_token",
        )
        for key in _stat_keys:
            lbl = QLabel("\u2014")
            lbl.setObjectName("statLabel")
            stats_layout.addWidget(lbl)
            self._stat_labels[key] = lbl

        self._stat_labels["tokens_in"].setText("in: \u2014")
        self._stat_labels["tokens_out"].setText("out: \u2014")
        self._stat_labels["tokens_think"].setText("think: \u2014")
        self._stat_labels["cost"].setText("$\u2014")
        self._stat_labels["context"].setText("ctx: \u2014")
        self._stat_labels["time"].setText("\u2014")
        self._stat_labels["first_token"].setText("\u2014")

        layout.addWidget(self._stats_bar)

        self._cost_warning_label = QLabel("")
        self._cost_warning_label.setObjectName("costWarning")
        self._cost_warning_label.setVisible(False)
        layout.addWidget(self._cost_warning_label)

        self._context_warning_label = QLabel("")
        self._context_warning_label.setObjectName("contextWarning")
        self._context_warning_label.setVisible(False)
        layout.addWidget(self._context_warning_label)

        self._options_btn = QPushButton("\u22ee")
        self._options_btn.setObjectName("actionBtn")
        self._options_btn.setFixedSize(28, 28)
        self._options_btn.clicked.connect(self._show_options_menu)
        layout.addWidget(self._options_btn)

        self._active_model_key = "auto"
        self._active_skill_id = "normal"

    def set_active_model(self, key: str) -> None:
        """Update the displayed model.

        Args:
            key: Registry key or ``"auto"``.
        """
        self._active_model_key = key
        if key == "auto":
            self._model_btn.setText("Emily \u2014 Auto \u25be")
        else:
            spec = EMILY_MODEL_REGISTRY.get(key)
            label = spec.display if spec else key
            self._model_btn.setText(f"{label} \u25be")

    def set_active_skill(self, skill_id: str) -> None:
        """Update the displayed skill.

        Args:
            skill_id: Skill key from ``EMILY_SKILLS``.
        """
        self._active_skill_id = skill_id
        skill = EMILY_SKILLS.get(skill_id)
        if skill:
            self._skill_btn.setText(f"{skill.icon} {skill.name} \u25be")
        else:
            self._skill_btn.setText("Normal \u25be")

    def set_live_stats(self, data: dict[str, Any]) -> None:
        """Update live token/cost/context stats during streaming.

        Args:
            data: Dict with optional keys: ``input_tokens``, ``output_tokens``,
                ``tokens_thinking``, ``cost_usd``, ``context_pct``,
                ``latency_ms``, ``first_token_ms``.
        """
        if "input_tokens" in data:
            txt = f"in: {format_tokens(data['input_tokens'])}"
            self._stat_labels["tokens_in"].setText(txt)
        if "output_tokens" in data:
            txt = f"out: {format_tokens(data['output_tokens'])}"
            self._stat_labels["tokens_out"].setText(txt)
        if "tokens_thinking" in data:
            txt = f"think: {format_tokens(data['tokens_thinking'])}"
            self._stat_labels["tokens_think"].setText(txt)
        if "cost_usd" in data:
            cost = data["cost_usd"]
            self._stat_labels["cost"].setText(format_cost(cost))
            level = cost_warning_level(cost)
            if level != "none":
                self._cost_warning_label.setText(
                    f"{'Cost > $0.20!' if level == 'red' else 'Cost > $0.05'}"
                )
                self._cost_warning_label.setVisible(True)
            else:
                self._cost_warning_label.setVisible(False)
        if "context_pct" in data:
            pct = data["context_pct"]
            self._stat_labels["context"].setText(f"ctx: {pct:.0f}%")
            level = context_warning_level(pct)
            if level != "none":
                self._context_warning_label.setText(
                    f"{'Context > 90%!' if level == 'red' else 'Context > 75%'}"
                )
                self._context_warning_label.setVisible(True)
            else:
                self._context_warning_label.setVisible(False)
        if "latency_ms" in data:
            val = data["latency_ms"]
            if val is not None:
                self._stat_labels["time"].setText(f"{val / 1000:.1f}s")
        if "first_token_ms" in data:
            val = data["first_token_ms"]
            if val is not None:
                self._stat_labels["first_token"].setText(f"{val}ms first")

    def clear_stats(self) -> None:
        """Reset all stats to dashes."""
        prefixes = {
            "tokens_in": "in",
            "tokens_out": "out",
            "tokens_think": "think",
            "cost": "$",
            "context": "ctx",
        }
        for key, lbl in self._stat_labels.items():
            prefix = prefixes.get(key, "")
            lbl.setText(f"{prefix}: \u2014" if prefix else "\u2014")
        self._cost_warning_label.setVisible(False)
        self._context_warning_label.setVisible(False)

    def _show_model_menu(self) -> None:
        """Display the categorized model selector menu."""
        menu = QMenu(self)
        menu.setObjectName("modelSelectorMenu")

        auto_action = menu.addAction("\u26a1 Emily \u2014 Auto (Smart routing)")
        auto_action.triggered.connect(lambda: self._select_model("auto"))
        if self._active_model_key == "auto":
            auto_action.setEnabled(False)
        menu.addSeparator()

        for category, items in group_models():
            menu.addSection(category)
            for key, spec in items:
                cost_str = f"${spec.input_usd:.2f}/{spec.output_usd:.2f}"
                action = menu.addAction(f"{spec.display}  \u2014  {cost_str}  [{spec.speed}]")
                action.triggered.connect(lambda checked=False, k=key: self._select_model(k))
                if key == self._active_model_key:
                    action.setEnabled(False)

        menu.exec(self._model_btn.mapToGlobal(self._model_btn.rect().bottomLeft()))

    def _select_model(self, key: str) -> None:
        """Handle model selection.

        Args:
            key: Registry key or ``"auto"``.
        """
        self.set_active_model(key)
        self.model_changed.emit(key)

    def _show_skill_menu(self) -> None:
        """Display the skill selector menu."""
        menu = QMenu(self)

        normal_action = menu.addAction("Normal Chat")
        normal_action.triggered.connect(lambda: self._select_skill("normal"))
        if self._active_skill_id == "normal":
            normal_action.setEnabled(False)
        menu.addSeparator()

        for skill_id, skill in EMILY_SKILLS.items():
            action = menu.addAction(f"{skill.icon} {skill.name}")
            action.triggered.connect(lambda checked=False, sid=skill_id: self._select_skill(sid))
            if skill_id == self._active_skill_id:
                action.setEnabled(False)

        menu.exec(self._skill_btn.mapToGlobal(self._skill_btn.rect().bottomLeft()))

    def _select_skill(self, skill_id: str) -> None:
        """Handle skill selection.

        Args:
            skill_id: Skill key.
        """
        self.set_active_skill(skill_id)
        self.skill_changed.emit(skill_id)

    def _show_options_menu(self) -> None:
        """Display the options overflow menu."""
        menu = QMenu(self)
        menu.addAction("Emily Editor (Systems)", lambda: self.emily_editor_requested.emit())
        menu.addAction("Edit system prompt", lambda: self.system_prompt_edit_requested.emit())
        menu.addSeparator()
        menu.addAction("Clear conversation", lambda: self.clear_requested.emit())
        menu.addAction("Fork conversation", lambda: self.fork_requested.emit())
        menu.addAction("Duplicate conversation", lambda: self.fork_requested.emit())
        menu.addSeparator()

        export_menu = menu.addMenu("Export")
        for fmt in ("Markdown", "PDF", "HTML", "JSON"):
            export_menu.addAction(fmt, lambda f=fmt: self.export_requested.emit(f.lower()))

        menu.exec(self._options_btn.mapToGlobal(self._options_btn.rect().bottomLeft()))
