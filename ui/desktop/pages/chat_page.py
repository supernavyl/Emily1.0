"""App page — main chat interface with sidebar, chat area, and stats panel."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..widgets import ChatInput, MessageBubble, StatRow, ThinkingBubble

if TYPE_CHECKING:
    from ..api_client import EmilyAPIClient


class ChatPage(QWidget):
    """Full chat interface — sidebar + chat + right panel."""

    def __init__(self, api: EmilyAPIClient, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.api = api

        # State
        self._conversation_id = str(uuid.uuid4())
        self._messages: list[dict[str, str]] = []
        self._current_bubble: MessageBubble | None = None
        self._current_thinking: ThinkingBubble | None = None
        self._is_streaming = False
        self._total_cost = 0.0
        self._total_tokens = 0

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(True)

        splitter.addWidget(self._build_sidebar())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right_panel())

        splitter.setSizes([220, 900, 260])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        root.addWidget(splitter)

    # -- Sidebar --

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(280)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        new_chat_btn = QPushButton("+ New Chat")
        new_chat_btn.setObjectName("newChatBtn")
        new_chat_btn.clicked.connect(self._new_conversation)
        layout.addWidget(new_chat_btn)

        layout.addSpacing(12)

        skills_label = QLabel("SKILLS")
        skills_label.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 700; "
            f"padding: 4px 0; letter-spacing: 1px;"
        )
        layout.addWidget(skills_label)

        self._skill_buttons: dict[str, QPushButton] = {}
        for skill_id, label in [
            ("normal", "Chat"),
            ("deep-think", "Deep Think"),
            ("code", "Code"),
            ("research", "Research"),
            ("concise", "Concise"),
        ]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(skill_id == "normal")
            btn.clicked.connect(lambda checked, sid=skill_id: self._select_skill(sid))
            layout.addWidget(btn)
            self._skill_buttons[skill_id] = btn

        layout.addStretch()
        return sidebar

    # -- Center --

    def _build_center(self) -> QWidget:
        center = QWidget()
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Model bar
        bar = QWidget()
        bar.setObjectName("topBar")
        bar.setFixedHeight(40)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 0, 16, 0)

        bar_layout.addWidget(QLabel("Model:"))
        self._model_combo = QComboBox()
        self._model_combo.setMinimumWidth(200)
        self._model_combo.addItem("auto (default)", "auto")
        bar_layout.addWidget(self._model_combo)
        bar_layout.addStretch()

        self._top_tokens = QLabel("")
        self._top_tokens.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        bar_layout.addWidget(self._top_tokens)
        self._top_cost = QLabel("")
        self._top_cost.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        bar_layout.addWidget(self._top_cost)
        self._top_latency = QLabel("")
        self._top_latency.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 11px;")
        bar_layout.addWidget(self._top_latency)

        layout.addWidget(bar)

        # Chat scroll
        self._chat_scroll = QScrollArea()
        self._chat_scroll.setObjectName("chatScroll")
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._chat_container = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(60, 20, 60, 20)
        self._chat_layout.setSpacing(16)
        self._chat_layout.addStretch()

        self._welcome = QLabel("Hi, I'm Emily. Ask me anything.")
        self._welcome.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 18px; padding: 60px 0;")
        self._welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chat_layout.insertWidget(0, self._welcome)

        self._chat_scroll.setWidget(self._chat_container)
        layout.addWidget(self._chat_scroll, 1)

        # Input
        input_panel = QWidget()
        input_panel.setObjectName("inputPanel")
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(60, 12, 60, 12)

        self._input = ChatInput()
        self._input.submitted.connect(self._on_submit)
        input_layout.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(80, 40)
        self._send_btn.clicked.connect(self._on_send_clicked)
        input_layout.addWidget(self._send_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setFixedSize(80, 40)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._on_stop)
        input_layout.addWidget(self._stop_btn)

        layout.addWidget(input_panel)
        return center

    # -- Right panel --

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("rightPanel")
        panel.setMinimumWidth(220)
        panel.setMaximumWidth(320)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)

        layout.addWidget(self._section_label("RESPONSE INFO"))
        self._stat_model = StatRow("Model")
        self._stat_provider = StatRow("Provider")
        self._stat_tokens_in = StatRow("Tokens in")
        self._stat_tokens_out = StatRow("Tokens out")
        self._stat_thinking = StatRow("Thinking tokens")
        self._stat_cost = StatRow("Cost")
        self._stat_latency = StatRow("Latency")
        for w in [
            self._stat_model,
            self._stat_provider,
            self._stat_tokens_in,
            self._stat_tokens_out,
            self._stat_thinking,
            self._stat_cost,
            self._stat_latency,
        ]:
            layout.addWidget(w)

        layout.addSpacing(16)
        layout.addWidget(self._section_label("SESSION"))
        self._stat_total_msgs = StatRow("Messages")
        self._stat_total_cost = StatRow("Total cost")
        self._stat_total_tokens = StatRow("Total tokens")
        for w in [self._stat_total_msgs, self._stat_total_cost, self._stat_total_tokens]:
            layout.addWidget(w)

        layout.addStretch()
        return panel

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1px; padding: 0 0 8px 0;"
        )
        return lbl

    # -- Signals --

    def _connect_signals(self) -> None:
        self.api.meta_received.connect(self._on_meta)
        self.api.text_received.connect(self._on_text)
        self.api.thinking_received.connect(self._on_thinking)
        self.api.usage_received.connect(self._on_usage)
        self.api.stream_error.connect(self._on_error)
        self.api.stream_done.connect(self._on_done)

    # -- Public: populate models combo from loaded data --

    def set_models(self, models: dict[str, Any]) -> None:
        self._model_combo.clear()
        self._model_combo.addItem("auto (smart routing)", "auto")
        for key, info in models.items():
            self._model_combo.addItem(info.get("display", key), key)

    def set_skills(self, skills: dict[str, Any]) -> None:
        for sid, info in skills.items():
            if sid not in self._skill_buttons:
                btn = QPushButton(info.get("name", sid))
                btn.setCheckable(True)
                btn.clicked.connect(lambda checked, s=sid: self._select_skill(s))
                sidebar = self.findChild(QWidget, "sidebar")
                if sidebar and sidebar.layout():
                    sidebar.layout().insertWidget(sidebar.layout().count() - 1, btn)
                self._skill_buttons[sid] = btn

    # -- Actions --

    def _on_submit(self, text: str) -> None:
        if not self._is_streaming:
            self._send_message(text)

    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if text and not self._is_streaming:
            self._input.clear()
            self._send_message(text)

    def _send_message(self, text: str) -> None:
        if self._welcome.isVisible():
            self._welcome.setVisible(False)

        self._insert_bubble(MessageBubble(text, role="user"))
        self._messages.append({"role": "user", "content": text})

        model_id = self._model_combo.currentData() or "auto"
        skill_id = next(
            (sid for sid, btn in self._skill_buttons.items() if btn.isChecked()), "normal"
        )

        self._is_streaming = True
        self._send_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._input.setReadOnly(True)
        self._current_bubble = None
        self._current_thinking = None

        self.api.send_message(
            message=text,
            model_id=model_id,
            skill_id=skill_id,
            messages=self._messages,
            conversation_id=self._conversation_id,
        )

    def _on_stop(self) -> None:
        self.api.abort_stream()
        self._finish_streaming()

    def _finish_streaming(self) -> None:
        self._is_streaming = False
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._input.setReadOnly(False)
        self._input.setFocus()
        if self._current_thinking:
            self._current_thinking.finalize()
        if self._current_bubble:
            self._messages.append(
                {"role": "assistant", "content": self._current_bubble.content_label.text()}
            )
        self._current_bubble = None
        self._current_thinking = None

    def _on_meta(self, data: dict) -> None:
        self._stat_model.set_value(data.get("display", data.get("model_id", "?")))
        self._stat_provider.set_value(data.get("provider", "?"))

    def _on_thinking(self, text: str) -> None:
        if not self._current_thinking:
            self._current_thinking = ThinkingBubble()
            self._insert_bubble(self._current_thinking)
        self._current_thinking.append_text(text)

    def _on_text(self, text: str) -> None:
        if not self._current_bubble:
            self._current_bubble = MessageBubble("", role="assistant")
            self._insert_bubble(self._current_bubble)
        self._current_bubble.append_text(text)
        self._scroll_to_bottom()

    def _on_usage(self, data: dict) -> None:
        ti = data.get("tokens_in", 0)
        to = data.get("tokens_out", 0)
        tt = data.get("tokens_thinking", 0)
        cost = data.get("cost_usd", 0)
        lat = data.get("latency_ms", 0)

        self._stat_tokens_in.set_value(f"{ti:,}")
        self._stat_tokens_out.set_value(f"{to:,}")
        self._stat_thinking.set_value(f"{tt:,}" if tt else "--")
        self._stat_cost.set_value(f"${cost:.4f}" if cost else "free")
        self._stat_latency.set_value(f"{lat:,}ms")

        self._top_tokens.setText(f"{ti + to:,} tok")
        self._top_cost.setText(f"  ${cost:.4f}" if cost else "  free")
        self._top_latency.setText(f"  {lat:,}ms")

        self._total_cost += cost
        self._total_tokens += ti + to
        self._stat_total_msgs.set_value(str(len(self._messages) + 1))
        self._stat_total_cost.set_value(f"${self._total_cost:.4f}" if self._total_cost else "free")
        self._stat_total_tokens.set_value(f"{self._total_tokens:,}")

    def _on_error(self, msg: str) -> None:
        lbl = QLabel(f"Error: {msg}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            f"color: {theme.ERROR_TEXT}; font-size: 13px; padding: 8px 16px; "
            f"background-color: #2d1b1b; border-radius: 8px;"
        )
        self._insert_bubble(lbl)
        self._finish_streaming()

    def _on_done(self) -> None:
        self._finish_streaming()

    def _new_conversation(self) -> None:
        self._conversation_id = str(uuid.uuid4())
        self._messages.clear()
        self._total_cost = 0.0
        self._total_tokens = 0
        while self._chat_layout.count() > 1:
            item = self._chat_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._welcome.setVisible(True)
        for stat in [
            self._stat_model,
            self._stat_provider,
            self._stat_tokens_in,
            self._stat_tokens_out,
            self._stat_thinking,
            self._stat_cost,
            self._stat_latency,
            self._stat_total_msgs,
            self._stat_total_cost,
            self._stat_total_tokens,
        ]:
            stat.set_value("--")
        self._top_tokens.setText("")
        self._top_cost.setText("")
        self._top_latency.setText("")
        if self._is_streaming:
            self._on_stop()
        self._input.setFocus()

    def _select_skill(self, skill_id: str) -> None:
        for sid, btn in self._skill_buttons.items():
            btn.setChecked(sid == skill_id)

    def _insert_bubble(self, widget: QWidget) -> None:
        self._chat_layout.insertWidget(self._chat_layout.count() - 1, widget)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            10,
            lambda: self._chat_scroll.verticalScrollBar().setValue(
                self._chat_scroll.verticalScrollBar().maximum()
            ),
        )
