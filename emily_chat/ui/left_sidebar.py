"""Left sidebar: conversation list, search, skills navigation, and quick actions.

All visual styling comes from the active QSS theme — zero hardcoded colours
except the provider colour-dot map which is intentionally data-driven.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from emily_chat.storage.models import ConversationSummary

# ── Provider colour dots ──────────────────────────────────────────────

PROVIDER_COLORS: dict[str, str] = {
    "anthropic": "#d97706",
    "openai": "#10b981",
    "google": "#3b82f6",
    "xai": "#8b5cf6",
    "deepseek": "#06b6d4",
    "groq": "#f97316",
    "mistral": "#ef4444",
    "together": "#ec4899",
    "openrouter": "#a855f7",
    "ollama": "#22c55e",
}

# ── Built-in skills (display-only; no inline prompts) ────────────────

BUILT_IN_SKILLS: list[dict[str, str]] = [
    {
        "id": "deep_think",
        "icon": "\U0001f9e0",
        "name": "Deep Think",
        "description": "Emily reasons step-by-step before answering",
    },
    {
        "id": "code",
        "icon": "\U0001f4bb",
        "name": "Code",
        "description": "Emily writes, reviews, and debugs code",
    },
    {
        "id": "research",
        "icon": "\U0001f52c",
        "name": "Research",
        "description": "Emily searches the web and synthesizes sources",
    },
    {
        "id": "writing",
        "icon": "\u270d\ufe0f",
        "name": "Writing",
        "description": "Emily writes and edits with craft and style",
    },
    {
        "id": "concise",
        "icon": "\u26a1",
        "name": "Concise",
        "description": "Emily keeps it short and sharp",
    },
    {
        "id": "analyst",
        "icon": "\U0001f4ca",
        "name": "Analyst",
        "description": "Emily breaks down complexity systematically",
    },
    {
        "id": "tutor",
        "icon": "\U0001f393",
        "name": "Tutor",
        "description": "Emily teaches through questions and examples",
    },
    {
        "id": "debate",
        "icon": "\U0001f608",
        "name": "Devil's Advocate",
        "description": "Emily argues the strongest opposing position",
    },
    {
        "id": "translate",
        "icon": "\U0001f30d",
        "name": "Translate",
        "description": "Emily translates between any languages",
    },
    {
        "id": "brainstorm",
        "icon": "\U0001f4a1",
        "name": "Brainstorm",
        "description": "Emily generates bold, diverse ideas",
    },
    {
        "id": "eli5",
        "icon": "\U0001f9d2",
        "name": "Simple (ELI5)",
        "description": "Emily explains anything simply",
    },
    {
        "id": "compare",
        "icon": "\u2696\ufe0f",
        "name": "Compare Models",
        "description": "Send the same message to multiple Emily engines",
    },
]


# =====================================================================
# Date-grouping helpers (pure functions — easy to test without Qt)
# =====================================================================


def group_conversations(
    conversations: list[ConversationSummary],
) -> OrderedDict[str, list[ConversationSummary]]:
    """Sort *conversations* into date buckets for sidebar display.

    Bucket order: PINNED, TODAY, YESTERDAY, THIS WEEK, THIS MONTH,
    then ``Month Year`` for older entries.
    """
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    pinned: list[ConversationSummary] = []
    today: list[ConversationSummary] = []
    yesterday: list[ConversationSummary] = []
    this_week: list[ConversationSummary] = []
    this_month: list[ConversationSummary] = []
    older: dict[str, list[ConversationSummary]] = {}

    for conv in conversations:
        ts = conv.updated_at
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)

        if conv.pinned:
            pinned.append(conv)
        elif ts >= today_start:
            today.append(conv)
        elif ts >= yesterday_start:
            yesterday.append(conv)
        elif ts >= week_start:
            this_week.append(conv)
        elif ts >= month_start:
            this_month.append(conv)
        else:
            label = ts.strftime("%B %Y")
            older.setdefault(label, []).append(conv)

    buckets: OrderedDict[str, list[ConversationSummary]] = OrderedDict()
    if pinned:
        buckets["PINNED"] = pinned
    if today:
        buckets["TODAY"] = today
    if yesterday:
        buckets["YESTERDAY"] = yesterday
    if this_week:
        buckets["THIS WEEK"] = this_week
    if this_month:
        buckets["THIS MONTH"] = this_month
    for label in sorted(older, key=lambda lbl: older[lbl][0].updated_at, reverse=True):
        buckets[label] = older[label]

    return buckets


def relative_time(dt: datetime) -> str:
    """Human-friendly relative timestamp for sidebar items."""
    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = now - dt
    seconds = int(delta.total_seconds())

    if seconds < 60:
        return "just now"
    if seconds < 3600:
        m = seconds // 60
        return f"{m}m ago"
    if seconds < 86400:
        h = seconds // 3600
        return f"{h}h ago"
    if seconds < 172800:
        return "Yesterday"
    if seconds < 604800:
        d = seconds // 86400
        return f"{d}d ago"
    return dt.strftime("%b %d")


# =====================================================================
# Widgets
# =====================================================================


class _ProviderDot(QWidget):
    """8px coloured circle indicating the model provider."""

    def __init__(self, color: str = "#555570", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(8, 8)

    def set_color(self, hex_color: str) -> None:
        """Update the dot colour."""
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, _event: object) -> None:
        """Draw a filled circle."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 8, 8)
        p.end()


class ConversationItemWidget(QWidget):
    """A single row in the conversation list."""

    selected = Signal(str)  # conversation_id
    rename_requested = Signal(str)
    pin_requested = Signal(str, bool)
    duplicate_requested = Signal(str)
    fork_requested = Signal(str)
    archive_requested = Signal(str)
    delete_requested = Signal(str)
    export_requested = Signal(str, str)

    def __init__(
        self,
        summary: ConversationSummary,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.summary = summary
        self.setObjectName("conversationItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(48)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._is_selected = False
        self._pending_delete_timer: QTimer | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 8, 4)
        layout.setSpacing(8)

        self._dot = _ProviderDot(PROVIDER_COLORS.get(self.summary.provider or "", "#555570"))
        layout.addWidget(self._dot)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self._title_label = QLabel(self.summary.title)
        self._title_label.setObjectName("convItemTitle")
        self._title_label.setWordWrap(False)
        text_col.addWidget(self._title_label)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        self._time_label = QLabel(relative_time(self.summary.updated_at))
        self._time_label.setObjectName("convItemTime")
        meta_row.addWidget(self._time_label)

        self._msg_count = QLabel(f"{self.summary.total_messages} msgs")
        self._msg_count.setObjectName("convItemMeta")
        meta_row.addWidget(self._msg_count)

        if self.summary.total_cost_usd > 0:
            cost_label = QLabel(f"${self.summary.total_cost_usd:.3f}")
            cost_label.setObjectName("convItemCost")
            meta_row.addWidget(cost_label)

        meta_row.addStretch()
        text_col.addLayout(meta_row)
        layout.addLayout(text_col, stretch=1)

        # Hover action buttons (hidden by default)
        self._hover_actions = QWidget()
        self._hover_actions.setObjectName("convHoverActions")
        ha_layout = QHBoxLayout(self._hover_actions)
        ha_layout.setContentsMargins(0, 0, 0, 0)
        ha_layout.setSpacing(2)

        pin_icon = "\u274c" if self.summary.pinned else "\U0001f4cc"
        self._pin_btn = QPushButton(pin_icon)
        self._pin_btn.setObjectName("convActionBtn")
        self._pin_btn.setFixedSize(24, 24)
        self._pin_btn.setToolTip("Unpin" if self.summary.pinned else "Pin")
        self._pin_btn.clicked.connect(
            lambda: self.pin_requested.emit(self.summary.id, not self.summary.pinned)
        )
        ha_layout.addWidget(self._pin_btn)

        del_btn = QPushButton("\U0001f5d1")
        del_btn.setObjectName("convActionBtn")
        del_btn.setFixedSize(24, 24)
        del_btn.setToolTip("Delete")
        del_btn.clicked.connect(self._start_delete)
        ha_layout.addWidget(del_btn)

        layout.addWidget(self._hover_actions)
        self._hover_actions.hide()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def set_selected(self, selected: bool) -> None:
        """Toggle the visual selected state."""
        self._is_selected = selected
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def update_summary(self, summary: ConversationSummary) -> None:
        """Refresh displayed data from an updated summary."""
        self.summary = summary
        self._title_label.setText(summary.title)
        self._time_label.setText(relative_time(summary.updated_at))
        self._msg_count.setText(f"{summary.total_messages} msgs")
        self._dot.set_color(PROVIDER_COLORS.get(summary.provider or "", "#555570"))

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def enterEvent(self, _event: object) -> None:
        """Show hover action buttons."""
        self._hover_actions.show()

    def leaveEvent(self, _event: object) -> None:
        """Hide hover action buttons."""
        self._hover_actions.hide()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.summary.id)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        menu = QMenu(self)

        menu.addAction("Rename", lambda: self.rename_requested.emit(self.summary.id))

        pin_label = "Unpin" if self.summary.pinned else "Pin"
        menu.addAction(
            pin_label,
            lambda: self.pin_requested.emit(self.summary.id, not self.summary.pinned),
        )

        menu.addSeparator()
        menu.addAction("Duplicate", lambda: self.duplicate_requested.emit(self.summary.id))
        menu.addAction("Fork from here", lambda: self.fork_requested.emit(self.summary.id))

        export_menu = menu.addMenu("Export")
        for fmt in ("Markdown", "PDF", "HTML", "JSON"):
            export_menu.addAction(
                fmt,
                lambda f=fmt: self.export_requested.emit(self.summary.id, f.lower()),
            )

        menu.addSeparator()
        menu.addAction("Archive", lambda: self.archive_requested.emit(self.summary.id))
        menu.addAction("Delete", self._start_delete)

        menu.exec(event.globalPos())

    def _start_delete(self) -> None:
        """Hide immediately and start a 5s timer before emitting delete."""
        self.hide()
        self._pending_delete_timer = QTimer(self)
        self._pending_delete_timer.setSingleShot(True)
        self._pending_delete_timer.timeout.connect(self._confirm_delete)
        self._pending_delete_timer.start(5000)
        self.delete_requested.emit(self.summary.id)

    def cancel_delete(self) -> None:
        """Called by an undo toast to abort the pending deletion."""
        if self._pending_delete_timer is not None:
            self._pending_delete_timer.stop()
            self._pending_delete_timer = None
        self.show()

    def _confirm_delete(self) -> None:
        self._pending_delete_timer = None
        self.deleteLater()


class DateGroupWidget(QWidget):
    """Collapsible section header + child conversation items."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dateGroup")
        self._collapsed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._header = QPushButton(f"  {label}")
        self._header.setObjectName("dateGroupHeader")
        self._header.setFixedHeight(28)
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.clicked.connect(self._toggle)
        root.addWidget(self._header)

        self._container = QWidget()
        self._container.setObjectName("dateGroupContainer")
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(0)
        root.addWidget(self._container)

    def add_item(self, widget: QWidget) -> None:
        """Append a conversation-item widget to this group."""
        self._container_layout.addWidget(widget)

    def set_collapsed(self, collapsed: bool) -> None:
        """Programmatically collapse or expand."""
        self._collapsed = collapsed
        self._container.setVisible(not collapsed)

    def _toggle(self) -> None:
        self.set_collapsed(not self._collapsed)


class SkillItem(QWidget):
    """A single skill entry in the skills panel."""

    activated = Signal(str)  # skill_id

    def __init__(self, skill: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._skill_id = skill["id"]
        self.setObjectName("skillItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setToolTip(skill["description"])

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 2, 8, 2)
        layout.setSpacing(6)

        icon_lbl = QLabel(skill["icon"])
        icon_lbl.setFixedWidth(20)
        layout.addWidget(icon_lbl)

        name_lbl = QLabel(skill["name"])
        name_lbl.setObjectName("skillName")
        layout.addWidget(name_lbl)
        layout.addStretch()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._skill_id)
        super().mousePressEvent(event)


class SkillsSection(QWidget):
    """Collapsible skills list for the sidebar."""

    skill_activated = Signal(str)
    custom_skill_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("skillsSection")
        self._collapsed = False
        self._active_skill: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(12, 0, 8, 4)

        self._toggle_btn = QPushButton("\u25be")
        self._toggle_btn.setObjectName("groupToggle")
        self._toggle_btn.setFixedSize(16, 16)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.clicked.connect(self._toggle)
        header.addWidget(self._toggle_btn)

        lbl = QLabel("SKILLS & MODES")
        lbl.setObjectName("groupLabel")
        header.addWidget(lbl)
        header.addStretch()
        root.addLayout(header)

        self._items_container = QWidget()
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(0)

        self._skill_widgets: dict[str, SkillItem] = {}
        for skill in BUILT_IN_SKILLS:
            w = SkillItem(skill)
            w.activated.connect(self._on_skill_clicked)
            self._items_layout.addWidget(w)
            self._skill_widgets[skill["id"]] = w

        self._custom_btn = QPushButton("+ Custom Skill\u2026")
        self._custom_btn.setObjectName("customSkillBtn")
        self._custom_btn.setFixedHeight(28)
        self._custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._custom_btn.clicked.connect(self.custom_skill_requested.emit)
        self._items_layout.addWidget(self._custom_btn)

        root.addWidget(self._items_container)

    def set_active_skill(self, skill_id: str | None) -> None:
        """Highlight the active skill and dim the rest."""
        self._active_skill = skill_id
        for sid, widget in self._skill_widgets.items():
            widget.setProperty("active", sid == skill_id)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def _on_skill_clicked(self, skill_id: str) -> None:
        self.set_active_skill(skill_id)
        self.skill_activated.emit(skill_id)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._items_container.setVisible(not self._collapsed)
        self._toggle_btn.setText("\u25b8" if self._collapsed else "\u25be")


class LeftSidebar(QWidget):
    """Full left sidebar: search, conversation list, skills, and footer."""

    new_conversation = Signal()
    conversation_selected = Signal(str)
    skill_activated = Signal(str)
    custom_skill_requested = Signal()
    search_requested = Signal(str)
    settings_requested = Signal()

    rename_requested = Signal(str)
    pin_requested = Signal(str, bool)
    duplicate_requested = Signal(str)
    fork_requested = Signal(str)
    archive_requested = Signal(str)
    delete_requested = Signal(str)
    export_requested = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("leftPanel")
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._collapsed_groups: set[str] = set()
        self._active_conversation_id: str | None = None
        self._item_map: dict[str, ConversationItemWidget] = {}
        self._groups: list[DateGroupWidget] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 8, 0, 4)
        root.setSpacing(4)

        # ── New conversation button ──────────────────────────────────
        self._new_btn = QPushButton("+ New Conversation")
        self._new_btn.setObjectName("newConversationBtn")
        self._new_btn.setFixedHeight(34)
        self._new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._new_btn.clicked.connect(self.new_conversation.emit)
        root.addWidget(self._new_btn)

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.new_conversation.emit)

        # ── Search bar ───────────────────────────────────────────────
        self._search_input = QLineEdit()
        self._search_input.setObjectName("sidebarSearch")
        self._search_input.setPlaceholderText("Search conversations\u2026")
        self._search_input.setClearButtonEnabled(True)
        root.addWidget(self._search_input)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(150)
        self._search_timer.timeout.connect(
            lambda: self.search_requested.emit(self._search_input.text())
        )
        self._search_input.textChanged.connect(lambda _: self._search_timer.start())

        # ── Conversation list (scroll area) ──────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setObjectName("convListScroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._conv_container = QWidget()
        self._conv_layout = QVBoxLayout(self._conv_container)
        self._conv_layout.setContentsMargins(0, 0, 0, 0)
        self._conv_layout.setSpacing(0)
        self._conv_layout.addStretch()
        self._scroll.setWidget(self._conv_container)

        root.addWidget(self._scroll, stretch=1)

        # ── Skills section ───────────────────────────────────────────
        self._skills = SkillsSection()
        self._skills.skill_activated.connect(self.skill_activated.emit)
        self._skills.custom_skill_requested.connect(self.custom_skill_requested.emit)
        root.addWidget(self._skills)

        # ── Footer ───────────────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setContentsMargins(12, 4, 12, 4)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("sidebarFooterBtn")
        settings_btn.setFlat(True)
        settings_btn.clicked.connect(self.settings_requested.emit)
        footer.addWidget(settings_btn)

        footer.addStretch()

        version_label = QLabel("v0.1.0")
        version_label.setObjectName("sidebarVersion")
        footer.addWidget(version_label)

        root.addLayout(footer)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def populate(
        self,
        conversations: list[ConversationSummary],
        collapsed_groups: set[str] | None = None,
    ) -> None:
        """Rebuild the conversation list from a fresh list of summaries."""
        if collapsed_groups is not None:
            self._collapsed_groups = collapsed_groups

        self._clear_groups()
        self._item_map.clear()

        groups = group_conversations(conversations)
        stretch = self._conv_layout.takeAt(self._conv_layout.count() - 1)

        for label, convs in groups.items():
            group_w = DateGroupWidget(label)
            if label in self._collapsed_groups:
                group_w.set_collapsed(True)
            for conv in convs:
                item = ConversationItemWidget(conv)
                item.selected.connect(self._on_item_clicked)
                item.rename_requested.connect(self.rename_requested.emit)
                item.pin_requested.connect(self.pin_requested.emit)
                item.duplicate_requested.connect(self.duplicate_requested.emit)
                item.fork_requested.connect(self.fork_requested.emit)
                item.archive_requested.connect(self.archive_requested.emit)
                item.delete_requested.connect(self.delete_requested.emit)
                item.export_requested.connect(self.export_requested.emit)
                group_w.add_item(item)
                self._item_map[conv.id] = item
            self._groups.append(group_w)
            self._conv_layout.addWidget(group_w)

        if stretch is not None:
            self._conv_layout.addStretch()

        if self._active_conversation_id and self._active_conversation_id in self._item_map:
            self._item_map[self._active_conversation_id].set_selected(True)

    def select_conversation(self, conversation_id: str) -> None:
        """Highlight a conversation by id."""
        if self._active_conversation_id and self._active_conversation_id in self._item_map:
            self._item_map[self._active_conversation_id].set_selected(False)
        self._active_conversation_id = conversation_id
        if conversation_id in self._item_map:
            self._item_map[conversation_id].set_selected(True)

    def set_active_skill(self, skill_id: str | None) -> None:
        """Highlight the given skill in the skills panel."""
        self._skills.set_active_skill(skill_id)

    def focus_search(self) -> None:
        """Move keyboard focus to the search input."""
        self._search_input.setFocus()
        self._search_input.selectAll()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_item_clicked(self, conversation_id: str) -> None:
        self.select_conversation(conversation_id)
        self.conversation_selected.emit(conversation_id)

    def _clear_groups(self) -> None:
        for group in self._groups:
            self._conv_layout.removeWidget(group)
            group.deleteLater()
        self._groups.clear()
