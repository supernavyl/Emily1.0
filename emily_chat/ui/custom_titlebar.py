"""
Custom frameless title bar for the Emily Chat window.

Provides drag-to-move, double-click maximize/restore, and
styled minimize / maximize / close buttons.  All visual styling
comes from the active QSS theme -- zero hardcoded colours here.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)


class CustomTitleBar(QWidget):
    """Frameless window title bar with drag, double-click, and window controls."""

    TITLE_BAR_HEIGHT = 38

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("customTitleBar")
        self.setFixedHeight(self.TITLE_BAR_HEIGHT)
        self._drag_pos: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        self._icon_label = QLabel()
        self._icon_label.setObjectName("titleBarIcon")
        self._icon_label.setFixedSize(18, 18)
        layout.addWidget(self._icon_label)

        self._title_label = QLabel("EMILY CHAT")
        self._title_label.setObjectName("titleBarTitle")
        layout.addWidget(self._title_label)

        layout.addStretch()

        self._btn_minimize = self._make_button("titleBtnMinimize", "\u2013")
        self._btn_maximize = self._make_button("titleBtnMaximize", "\u25a1")
        self._btn_close = self._make_button("titleBtnClose", "\u2715")

        layout.addWidget(self._btn_minimize)
        layout.addWidget(self._btn_maximize)
        layout.addWidget(self._btn_close)

        self._btn_minimize.clicked.connect(self._on_minimize)
        self._btn_maximize.clicked.connect(self._on_maximize)
        self._btn_close.clicked.connect(self._on_close)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_button(object_name: str, text: str) -> QPushButton:
        """Create a styled window-control button."""
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFixedSize(36, 28)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return btn

    def _host_window(self) -> QWidget:
        """Return the top-level window that owns this title bar."""
        return self.window()

    # ------------------------------------------------------------------
    # Button actions
    # ------------------------------------------------------------------

    def _on_minimize(self) -> None:
        self._host_window().showMinimized()

    def _on_maximize(self) -> None:
        win = self._host_window()
        if win.isMaximized():
            win.showNormal()
            self._btn_maximize.setText("\u25a1")
        else:
            win.showMaximized()
            self._btn_maximize.setText("\u25a3")

    def _on_close(self) -> None:
        self._host_window().close()

    # ------------------------------------------------------------------
    # Drag-to-move & double-click
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Begin drag on left-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._host_window().pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Move window while dragging."""
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            win = self._host_window()
            if win.isMaximized():
                win.showNormal()
                self._btn_maximize.setText("\u25a1")
                self._drag_pos = QPoint(win.width() // 2, self.TITLE_BAR_HEIGHT // 2)
            win.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """End drag."""
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Toggle maximise on double-click."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_maximize()
