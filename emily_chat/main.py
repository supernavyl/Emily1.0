"""
Emily Chat desktop application entry point.

Creates the QApplication, loads bundled fonts, applies the theme,
and launches the main window with database-backed conversation list.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from emily_chat.config import AppSettings

_ASSETS_DIR = Path(__file__).parent / "assets"
_FONTS_DIR = _ASSETS_DIR / "fonts"


def _load_bundled_fonts() -> None:
    """Register all .ttf files under assets/fonts/ with the font database."""
    if not _FONTS_DIR.is_dir():
        return
    for ttf in _FONTS_DIR.glob("*.ttf"):
        QFontDatabase.addApplicationFont(str(ttf))


def main() -> None:
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Emily Chat")
    app.setOrganizationName("Emily")
    app.setApplicationVersion("0.1.0")

    _load_bundled_fonts()

    settings = AppSettings.load()

    from emily_chat.ui.theme_engine import ThemeEngine
    from emily_chat.ui.main_window import MainWindow
    from emily_chat.ui.system_tray import SystemTrayManager
    from emily_chat.controller import ChatController

    theme_engine = ThemeEngine(app)
    theme_engine.apply_theme(settings.theme)

    window = MainWindow(settings=settings, theme_engine=theme_engine)

    tray = SystemTrayManager(window=window)
    window.set_tray(tray)

    controller = ChatController(
        sidebar=window.sidebar,
        conversation_stream=window.conversation_stream,
        input_panel=window.input_panel,
        right_panel=window.right_panel,
        settings=settings,
        top_bar=window.top_bar,
        search_overlay=window.search_overlay,
        parent=window,
    )
    controller.start()

    app.aboutToQuit.connect(controller.shutdown)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
