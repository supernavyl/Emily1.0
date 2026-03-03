"""Emily Desktop — all-in-one PySide6 application with 4-page navigation.

Pages:
    App   — Chat interface with SSE streaming
    Voice — Voice mode controls and live transcript
    Logs  — Real-time log viewer and audit trail
    Brain — System status, models, agents, memory

Run with:
    uv run python -m ui.desktop
"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .api_client import EmilyAPIClient
from .pages.brain_page import BrainPage
from .pages.chat_page import ChatPage
from .pages.logs_page import LogsPage
from .pages.voice_page import VoicePage
from .theme import STYLESHEET


class EmilyDesktop(QMainWindow):
    """Main window — nav bar + 4 stacked pages."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Emily")
        self.setMinimumSize(900, 600)
        self.resize(1440, 900)

        # API client (shared across pages)
        self.api = EmilyAPIClient(parent=self)

        # Build UI
        self._build_ui()
        self.setStyleSheet(STYLESHEET)

        # Wire up API data to pages
        self.api.models_loaded.connect(self._on_models_loaded)
        self.api.skills_loaded.connect(self._on_skills_loaded)
        self.api.health_received.connect(self._on_health)

        # Fetch initial data
        QTimer.singleShot(100, self._fetch_initial_data)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # -- Navigation bar --
        root.addWidget(self._build_nav_bar())

        # -- Stacked pages --
        self._stack = QStackedWidget()

        self._chat_page = ChatPage(self.api)
        self._voice_page = VoicePage()
        self._logs_page = LogsPage()
        self._brain_page = BrainPage()

        self._stack.addWidget(self._chat_page)  # index 0
        self._stack.addWidget(self._voice_page)  # index 1
        self._stack.addWidget(self._logs_page)  # index 2
        self._stack.addWidget(self._brain_page)  # index 3

        root.addWidget(self._stack, 1)

    def _build_nav_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("navBar")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(0)

        # Logo
        logo = QLabel("Emily")
        logo.setObjectName("navLogo")
        layout.addWidget(logo)

        # Nav buttons
        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("App", 0),
            ("Voice", 1),
            ("Logs", 2),
            ("Brain", 3),
        ]

        for label, index in nav_items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(index == 0)
            btn.clicked.connect(lambda checked, i=index: self._switch_page(i))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch()

        # Connection indicator
        self._connection_dot = QLabel("")
        self._connection_dot.setFixedSize(8, 8)
        self._connection_dot.setStyleSheet(
            f"background-color: {theme.WARNING}; border-radius: 4px;"
        )
        layout.addWidget(self._connection_dot)

        self._connection_label = QLabel("Connecting...")
        self._connection_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 11px; padding-left: 6px;"
        )
        layout.addWidget(self._connection_label)

        return bar

    def _switch_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)

    # -- API data distribution --

    def _fetch_initial_data(self) -> None:
        self.api.fetch_health()
        self.api.fetch_models()
        self.api.fetch_skills()

    def _on_models_loaded(self, data: dict) -> None:
        models = data.get("models", {})
        self._chat_page.set_models(models)

        self._connection_dot.setStyleSheet(
            f"background-color: {theme.SUCCESS}; border-radius: 4px;"
        )
        self._connection_label.setText(f"Connected  ({len(models)} models)")
        self._connection_label.setStyleSheet(
            f"color: {theme.SUCCESS}; font-size: 11px; padding-left: 6px;"
        )

    def _on_skills_loaded(self, data: dict) -> None:
        skills = data.get("skills", {})
        self._chat_page.set_skills(skills)

    def _on_health(self, data: dict) -> None:
        uptime = data.get("uptime_s", 0)
        if uptime:
            self._connection_dot.setStyleSheet(
                f"background-color: {theme.SUCCESS}; border-radius: 4px;"
            )


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Emily")
    app.setStyle("Fusion")

    font = QFont("Inter", 13)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    window = EmilyDesktop()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
