"""Brain page — model registry, system status, memory, agents, and config."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import theme


class BrainPage(QWidget):
    """Brain dashboard — system overview, models, agents, memory, resources."""

    def __init__(self, base_url: str = "http://localhost:8000", parent: QWidget | None = None):
        super().__init__(parent)
        self._base_url = base_url
        self._nam = QNetworkAccessManager(self)

        self._build_ui()

        # Poll status every 5s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_all)
        self._timer.start(5000)

        QTimer.singleShot(200, self._refresh_all)

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setObjectName("chatScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header
        header = QLabel("Emily's Brain")
        header.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 22px; font-weight: 800;")
        layout.addWidget(header)

        # System resources row
        layout.addWidget(self._section("SYSTEM RESOURCES"))
        resources_grid = QGridLayout()
        resources_grid.setSpacing(12)

        self._cpu_card = self._resource_card("CPU", "0%")
        self._ram_card = self._resource_card("RAM", "0 / 0 GB")
        self._vram_card = self._resource_card("VRAM", "0 / 0 MB")
        self._uptime_card = self._resource_card("Uptime", "0s")

        resources_grid.addWidget(self._cpu_card, 0, 0)
        resources_grid.addWidget(self._ram_card, 0, 1)
        resources_grid.addWidget(self._vram_card, 0, 2)
        resources_grid.addWidget(self._uptime_card, 0, 3)
        layout.addLayout(resources_grid)

        # FSM + Emotional state
        state_row = QHBoxLayout()

        # FSM state
        fsm_box = QVBoxLayout()
        fsm_box.addWidget(self._section("CONVERSATION FSM"))
        self._fsm_state = QLabel("UNKNOWN")
        self._fsm_state.setStyleSheet(
            f"color: {theme.ACCENT}; font-size: 18px; font-weight: 700; padding: 4px 0;"
        )
        fsm_box.addWidget(self._fsm_state)
        self._fsm_history = QLabel("")
        self._fsm_history.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
        self._fsm_history.setWordWrap(True)
        fsm_box.addWidget(self._fsm_history)
        state_row.addLayout(fsm_box, 1)

        # Emotional state
        emo_box = QVBoxLayout()
        emo_box.addWidget(self._section("EMOTIONAL STATE"))
        self._emo_bars: dict[str, tuple[QLabel, QProgressBar]] = {}
        for dim in ("engagement", "confidence", "concern", "enthusiasm"):
            row = QHBoxLayout()
            lbl = QLabel(dim.capitalize())
            lbl.setFixedWidth(100)
            lbl.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(50)
            bar.setFixedHeight(14)
            bar.setTextVisible(False)
            bar.setStyleSheet(
                f"QProgressBar {{ background: {theme.BG_TERTIARY}; border-radius: 7px; border: none; }}"
                f"QProgressBar::chunk {{ background: {theme.ACCENT}; border-radius: 7px; }}"
            )
            val_lbl = QLabel("0.50")
            val_lbl.setFixedWidth(40)
            val_lbl.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 12px;")
            row.addWidget(lbl)
            row.addWidget(bar, 1)
            row.addWidget(val_lbl)
            emo_box.addLayout(row)
            self._emo_bars[dim] = (val_lbl, bar)
        state_row.addLayout(emo_box, 1)

        layout.addLayout(state_row)

        # Agents
        layout.addWidget(self._section("AGENTS"))
        self._agents_container = QHBoxLayout()
        self._agents_container.setSpacing(8)
        # Placeholder
        self._agents_placeholder = QLabel("Loading agents...")
        self._agents_placeholder.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        self._agents_container.addWidget(self._agents_placeholder)
        self._agents_container.addStretch()
        layout.addLayout(self._agents_container)

        # Model Fleet
        layout.addWidget(self._section("MODEL FLEET"))
        self._models_grid = QGridLayout()
        self._models_grid.setSpacing(8)
        self._models_placeholder = QLabel("Loading models...")
        self._models_placeholder.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 13px;")
        self._models_grid.addWidget(self._models_placeholder, 0, 0)
        layout.addLayout(self._models_grid)

        # Metrics
        layout.addWidget(self._section("METRICS"))
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(8)

        self._metric_conversations = self._metric_card("Conversations", "0")
        self._metric_llm_requests = self._metric_card("LLM Requests", "0")
        self._metric_tool_calls = self._metric_card("Tool Calls", "0")
        self._metric_wake_words = self._metric_card("Wake Words", "0")
        self._metric_stt_errors = self._metric_card("STT Errors", "0")
        self._metric_rag_docs = self._metric_card("RAG Docs", "0")

        metrics_grid.addWidget(self._metric_conversations, 0, 0)
        metrics_grid.addWidget(self._metric_llm_requests, 0, 1)
        metrics_grid.addWidget(self._metric_tool_calls, 0, 2)
        metrics_grid.addWidget(self._metric_wake_words, 1, 0)
        metrics_grid.addWidget(self._metric_stt_errors, 1, 1)
        metrics_grid.addWidget(self._metric_rag_docs, 1, 2)
        layout.addLayout(metrics_grid)

        # Memory
        layout.addWidget(self._section("MEMORY"))
        mem_row = QHBoxLayout()
        self._mem_working = self._metric_card("Working Memory", "0 tokens")
        self._mem_episodic = self._metric_card("Episodic Sessions", "0")
        self._mem_queue = self._metric_card("Agent Queue", "0")
        mem_row.addWidget(self._mem_working)
        mem_row.addWidget(self._mem_episodic)
        mem_row.addWidget(self._mem_queue)
        layout.addLayout(mem_row)

        layout.addStretch()

        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # -- Widget builders --

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1px; padding: 8px 0 4px 0;"
        )
        return lbl

    def _resource_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {theme.BG_SECONDARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; padding: 12px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        t = QLabel(title)
        t.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px; border: none;")
        layout.addWidget(t)

        v = QLabel(value)
        v.setObjectName(f"resource_{title.lower()}")
        v.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 16px; font-weight: 700; border: none;"
        )
        layout.addWidget(v)

        card._value_label = v  # type: ignore[attr-defined]
        return card

    def _metric_card(self, title: str, value: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {theme.BG_SECONDARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; padding: 10px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        t = QLabel(title)
        t.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 11px; border: none;")
        layout.addWidget(t)

        v = QLabel(value)
        v.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 14px; font-weight: 600; border: none;"
        )
        layout.addWidget(v)

        card._value_label = v  # type: ignore[attr-defined]
        return card

    def _agent_chip(self, name: str, role: str, agent_type: str) -> QFrame:
        chip = QFrame()
        border_color = theme.ACCENT if agent_type == "core" else theme.THINKING_BORDER
        chip.setStyleSheet(
            f"QFrame {{ background-color: {theme.BG_TERTIARY}; "
            f"border: 1px solid {border_color}; border-radius: 6px; padding: 8px; }}"
        )
        layout = QVBoxLayout(chip)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        n = QLabel(name)
        n.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-size: 12px; font-weight: 600; border: none;"
        )
        layout.addWidget(n)

        r = QLabel(role)
        r.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 10px; border: none;")
        layout.addWidget(r)

        return chip

    # -- Data fetching --

    def _refresh_all(self) -> None:
        self._fetch_status()
        self._fetch_agents()
        self._fetch_models()
        self._fetch_memory()

    def _fetch_status(self) -> None:
        url = QUrl(f"{self._base_url}/status")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_status(reply))

    def _handle_status(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())

            # FSM
            self._fsm_state.setText(data.get("fsm_state", "UNKNOWN"))
            history = data.get("fsm_history", [])
            if history:
                self._fsm_history.setText(" -> ".join(f"{f}->{t}" for f, t in history[-5:]))

            # Resources
            res = data.get("resources", {})
            self._cpu_card._value_label.setText(f"{res.get('cpu_percent', 0):.0f}%")  # type: ignore[attr-defined]
            self._ram_card._value_label.setText(  # type: ignore[attr-defined]
                f"{res.get('ram_used_gb', 0):.1f} / {res.get('ram_total_gb', 0):.1f} GB"
            )
            vram_used = res.get("vram_used_mb", 0)
            vram_total = res.get("vram_total_mb", 0)
            self._vram_card._value_label.setText(  # type: ignore[attr-defined]
                f"{vram_used:,} / {vram_total:,} MB" if vram_total else "N/A"
            )
            self._uptime_card._value_label.setText(f"{data.get('uptime_s', 0):.0f}s")  # type: ignore[attr-defined]

            # Emotional state
            emo = data.get("emotional_state", {})
            for dim, (val_lbl, bar) in self._emo_bars.items():
                v = emo.get(dim, 0.5)
                val_lbl.setText(f"{v:.2f}")
                bar.setValue(int(v * 100))

            # Metrics
            m = data.get("metrics", {})
            self._metric_conversations._value_label.setText(
                str(int(m.get("conversations_total", 0)))
            )  # type: ignore[attr-defined]
            self._metric_llm_requests._value_label.setText(str(int(m.get("llm_requests_total", 0))))  # type: ignore[attr-defined]
            self._metric_tool_calls._value_label.setText(str(int(m.get("tool_calls_total", 0))))  # type: ignore[attr-defined]
            self._metric_wake_words._value_label.setText(str(int(m.get("wake_words_detected", 0))))  # type: ignore[attr-defined]
            self._metric_stt_errors._value_label.setText(str(int(m.get("stt_errors", 0))))  # type: ignore[attr-defined]
            self._metric_rag_docs._value_label.setText(str(int(m.get("rag_docs_ingested", 0))))  # type: ignore[attr-defined]
            self._mem_queue._value_label.setText(str(int(m.get("queue_depth", 0))))  # type: ignore[attr-defined]
            wm = m.get("working_memory_tokens", 0)
            self._mem_working._value_label.setText(f"{int(wm):,} tokens")  # type: ignore[attr-defined]

        except Exception:
            pass
        reply.deleteLater()

    def _fetch_agents(self) -> None:
        url = QUrl(f"{self._base_url}/agents")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_agents(reply))

    def _handle_agents(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            agents = data.get("agents", [])

            # Clear existing
            if self._agents_placeholder:
                self._agents_placeholder.setVisible(False)

            # Remove old chips
            while self._agents_container.count() > 0:
                item = self._agents_container.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            for agent in agents:
                chip = self._agent_chip(
                    agent.get("name", "?"),
                    agent.get("role", ""),
                    agent.get("type", "core"),
                )
                self._agents_container.addWidget(chip)
            self._agents_container.addStretch()

        except Exception:
            pass
        reply.deleteLater()

    def _fetch_models(self) -> None:
        url = QUrl(f"{self._base_url}/api/v1/models")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_models(reply))

    def _handle_models(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            models = data.get("models", {})

            # Clear
            if self._models_placeholder:
                self._models_placeholder.setVisible(False)
            while self._models_grid.count() > 0:
                item = self._models_grid.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            # Group by provider
            by_provider: dict[str, list[tuple[str, dict]]] = {}
            for key, info in models.items():
                prov = info.get("provider", "unknown")
                by_provider.setdefault(prov, []).append((key, info))

            row = 0
            col = 0
            for provider, model_list in sorted(by_provider.items()):
                card = self._provider_card(provider, model_list)
                self._models_grid.addWidget(card, row, col)
                col += 1
                if col >= 3:
                    col = 0
                    row += 1

        except Exception:
            pass
        reply.deleteLater()

    def _provider_card(self, provider: str, models: list[tuple[str, dict]]) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {theme.BG_SECONDARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel(f"{provider.upper()} ({len(models)})")
        title.setStyleSheet(
            f"color: {theme.ACCENT}; font-size: 12px; font-weight: 700; border: none;"
        )
        layout.addWidget(title)

        for key, info in models[:6]:
            name = QLabel(info.get("display", key))
            name.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 11px; border: none;")
            layout.addWidget(name)

        if len(models) > 6:
            more = QLabel(f"+{len(models) - 6} more")
            more.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 10px; border: none;")
            layout.addWidget(more)

        return card

    def _fetch_memory(self) -> None:
        url = QUrl(f"{self._base_url}/memory/episodic?n=5")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_memory(reply))

    def _handle_memory(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            total = data.get("total_count", 0)
            self._mem_episodic._value_label.setText(str(total))  # type: ignore[attr-defined]
        except Exception:
            pass
        reply.deleteLater()
