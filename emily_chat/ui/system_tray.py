"""
System tray icon for Emily Chat.

Provides a tray icon with a context menu to show/hide the window
and quit the application.  When the window is closed with the tray
active, it hides instead of quitting.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

if TYPE_CHECKING:
    from emily_chat.ui.main_window import MainWindow

_ICON_PATH = Path(__file__).parent.parent / "assets" / "icons" / "emily_avatar.png"


class SystemTrayManager(QSystemTrayIcon):
    """Manages the system-tray icon and its context menu."""

    def __init__(self, window: MainWindow) -> None:
        icon = QIcon(str(_ICON_PATH)) if _ICON_PATH.exists() else QIcon()
        super().__init__(icon, parent=window)
        self._window = window
        self._first_minimize_shown = False

        self._build_menu()
        self.activated.connect(self._on_activated)
        self.show()

    def _build_menu(self) -> None:
        """Create the right-click context menu."""
        menu = QMenu()

        self._toggle_action = QAction("Show / Hide", menu)
        self._toggle_action.triggered.connect(self._toggle_window)
        menu.addAction(self._toggle_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Toggle window visibility on left-click."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle_window()

    def _toggle_window(self) -> None:
        """Show or hide the main window."""
        if self._window.isVisible() and not self._window.isMinimized():
            self._window.hide()
        else:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()

    def _quit(self) -> None:
        """Fully exit the application (save state first)."""
        self._window._save_state()
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()

    def show_first_minimize_notice(self) -> None:
        """Show a balloon tip the first time the window hides to tray."""
        if self._first_minimize_shown:
            return
        self._first_minimize_shown = True
        self.showMessage(
            "Emily Chat",
            "Emily Chat is still running in the system tray.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
