"""
Main application window with frameless chrome and three-panel layout.

Handles edge-resize hit-testing, panel sizing, and geometry persistence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor, QMouseEvent, QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from emily_chat.config import AppSettings
from emily_chat.ui.conversation_stream import ConversationStream
from emily_chat.ui.custom_titlebar import CustomTitleBar
from emily_chat.ui.input_panel import InputPanel
from emily_chat.ui.left_sidebar import LeftSidebar
from emily_chat.ui.right_panel import RightPanel
from emily_chat.ui.search_overlay import GlobalSearchOverlay
from emily_chat.ui.top_bar import ConversationTopBar

if TYPE_CHECKING:
    from emily_chat.ui.system_tray import SystemTrayManager
    from emily_chat.ui.theme_engine import ThemeEngine

_EDGE_MARGIN = 6  # pixels from window border that trigger resize
_MIN_WINDOW = QSize(900, 600)


class _ResizeEdge:
    """Bit-flags for which edge(s) the cursor is near."""

    NONE = 0
    LEFT = 1
    RIGHT = 2
    TOP = 4
    BOTTOM = 8


class MainWindow(QMainWindow):
    """Frameless main window with custom title bar, three-panel splitter, and resize grips."""

    def __init__(
        self,
        settings: AppSettings,
        theme_engine: ThemeEngine,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._theme_engine = theme_engine
        self._tray: SystemTrayManager | None = None
        self._resize_edge = _ResizeEdge.NONE
        self._resize_origin: QPoint | None = None
        self._resize_geom: QRect | None = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(_MIN_WINDOW)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMouseTracking(True)

        self._build_ui()
        self._restore_geometry()
        self._setup_shortcuts()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble title bar + three-panel splitter."""
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._title_bar = CustomTitleBar(self)
        root_layout.addWidget(self._title_bar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(2)
        self._splitter.setChildrenCollapsible(False)

        # Left: sidebar
        self._sidebar = LeftSidebar()

        # Centre: conversation stream + input panel
        self._center_panel = QWidget()
        self._center_panel.setObjectName("centerPanel")
        center_layout = QVBoxLayout(self._center_panel)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        self._top_bar = ConversationTopBar()
        self._conversation_stream = ConversationStream()
        self._input_panel = InputPanel()
        center_layout.addWidget(self._top_bar, stretch=0)
        center_layout.addWidget(self._conversation_stream, stretch=1)
        center_layout.addWidget(self._input_panel, stretch=0)

        # Right: thinking + metadata
        self._right_panel = RightPanel()

        self._splitter.addWidget(self._sidebar)
        self._splitter.addWidget(self._center_panel)
        self._splitter.addWidget(self._right_panel)

        self._center_panel.setMinimumWidth(300)

        self._restore_panel_sizes()
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setStretchFactor(2, 0)

        root_layout.addWidget(self._splitter)

        self._search_overlay = GlobalSearchOverlay(central)
        self._search_overlay.setGeometry(central.rect())

    @property
    def sidebar(self) -> LeftSidebar:
        """The left sidebar widget."""
        return self._sidebar

    @property
    def conversation_stream(self) -> ConversationStream:
        """The centre conversation stream widget."""
        return self._conversation_stream

    @property
    def input_panel(self) -> InputPanel:
        """The message input panel."""
        return self._input_panel

    @property
    def right_panel(self) -> RightPanel:
        """The right thinking/metadata panel."""
        return self._right_panel

    @property
    def top_bar(self) -> ConversationTopBar:
        """The conversation top bar widget."""
        return self._top_bar

    @property
    def search_overlay(self) -> GlobalSearchOverlay:
        """The global search overlay widget."""
        return self._search_overlay

    # ------------------------------------------------------------------
    # Tray integration
    # ------------------------------------------------------------------

    def set_tray(self, tray: SystemTrayManager) -> None:
        """Attach the system-tray manager (called from main.py after construction)."""
        self._tray = tray

    # ------------------------------------------------------------------
    # Geometry & panel persistence
    # ------------------------------------------------------------------

    def _restore_geometry(self) -> None:
        """Restore window position and size from saved settings."""
        s = self._settings
        if s.maximized:
            self.showMaximized()
        else:
            self.setGeometry(s.window_x, s.window_y, s.window_width, s.window_height)

    def _restore_panel_sizes(self) -> None:
        """Apply saved panel widths to the splitter."""
        s = self._settings
        left = s.left_panel_width
        right = s.right_panel_width if s.right_panel_visible else 0
        center = max(300, self.width() - left - right)
        self._splitter.setSizes([left, center, right])
        if not s.right_panel_visible:
            self._right_panel.hide()

    def _save_state(self) -> None:
        """Persist current geometry and panel sizes to settings."""
        s = self._settings
        s.maximized = self.isMaximized()
        if not s.maximized:
            geo = self.geometry()
            s.window_x = geo.x()
            s.window_y = geo.y()
            s.window_width = geo.width()
            s.window_height = geo.height()

        sizes = self._splitter.sizes()
        if len(sizes) == 3:
            s.left_panel_width = sizes[0]
            s.right_panel_width = sizes[2]
            s.right_panel_visible = sizes[2] > 0 and self._right_panel.isVisible()
        s.save()

    # ------------------------------------------------------------------
    # Shortcuts
    # ------------------------------------------------------------------

    def _setup_shortcuts(self) -> None:
        """Register application-level keyboard shortcuts."""
        toggle_shortcut = QShortcut(QKeySequence("Ctrl+Shift+E"), self)
        toggle_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        toggle_shortcut.activated.connect(self._toggle_visibility)

        search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        search_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        search_shortcut.activated.connect(self._search_overlay.toggle)

        new_chat_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        new_chat_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        new_chat_shortcut.activated.connect(self._sidebar.new_conversation.emit)

    def _toggle_visibility(self) -> None:
        """Show or hide the main window."""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def resizeEvent(self, event: QEvent) -> None:
        """Keep the search overlay sized to the window."""
        super().resizeEvent(event)
        central = self.centralWidget()
        if central and hasattr(self, "_search_overlay"):
            self._search_overlay.setGeometry(central.rect())

    def closeEvent(self, event: QEvent) -> None:
        """Save state on close; minimise to tray if available."""
        self._save_state()
        if self._tray is not None and self._tray.isVisible():
            event.ignore()
            self.hide()
            self._tray.show_first_minimize_notice()
        else:
            event.accept()

    # ------------------------------------------------------------------
    # Edge-resize hit-testing
    # ------------------------------------------------------------------

    def _edge_at(self, pos: QPoint) -> int:
        """Return _ResizeEdge flags for a local position."""
        rect = self.rect()
        edge = _ResizeEdge.NONE
        if pos.x() <= _EDGE_MARGIN:
            edge |= _ResizeEdge.LEFT
        if pos.x() >= rect.width() - _EDGE_MARGIN:
            edge |= _ResizeEdge.RIGHT
        if pos.y() <= _EDGE_MARGIN:
            edge |= _ResizeEdge.TOP
        if pos.y() >= rect.height() - _EDGE_MARGIN:
            edge |= _ResizeEdge.BOTTOM
        return edge

    @staticmethod
    def _cursor_for_edge(edge: int) -> Qt.CursorShape:
        """Map edge flags to a cursor shape."""
        mapping = {
            _ResizeEdge.LEFT: Qt.CursorShape.SizeHorCursor,
            _ResizeEdge.RIGHT: Qt.CursorShape.SizeHorCursor,
            _ResizeEdge.TOP: Qt.CursorShape.SizeVerCursor,
            _ResizeEdge.BOTTOM: Qt.CursorShape.SizeVerCursor,
            _ResizeEdge.LEFT | _ResizeEdge.TOP: Qt.CursorShape.SizeFDiagCursor,
            _ResizeEdge.RIGHT | _ResizeEdge.BOTTOM: Qt.CursorShape.SizeFDiagCursor,
            _ResizeEdge.RIGHT | _ResizeEdge.TOP: Qt.CursorShape.SizeBDiagCursor,
            _ResizeEdge.LEFT | _ResizeEdge.BOTTOM: Qt.CursorShape.SizeBDiagCursor,
        }
        return mapping.get(edge, Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Start edge resize on left-click in the border zone."""
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge != _ResizeEdge.NONE and not self.isMaximized():
                self._resize_edge = edge
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle resize dragging or cursor updates."""
        if self._resize_edge != _ResizeEdge.NONE and self._resize_origin is not None:
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
            return

        edge = self._edge_at(event.position().toPoint())
        if edge != _ResizeEdge.NONE and not self.isMaximized():
            self.setCursor(QCursor(self._cursor_for_edge(edge)))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Finish resize."""
        self._resize_edge = _ResizeEdge.NONE
        self._resize_origin = None
        self._resize_geom = None
        super().mouseReleaseEvent(event)

    def _do_resize(self, global_pos: QPoint) -> None:
        """Apply incremental resize based on mouse movement."""
        if self._resize_origin is None or self._resize_geom is None:
            return

        dx = global_pos.x() - self._resize_origin.x()
        dy = global_pos.y() - self._resize_origin.y()
        geo = QRect(self._resize_geom)
        min_w, min_h = _MIN_WINDOW.width(), _MIN_WINDOW.height()

        if self._resize_edge & _ResizeEdge.LEFT:
            new_w = max(min_w, geo.width() - dx)
            geo.setLeft(geo.right() - new_w)
        if self._resize_edge & _ResizeEdge.RIGHT:
            geo.setWidth(max(min_w, geo.width() + dx))
        if self._resize_edge & _ResizeEdge.TOP:
            new_h = max(min_h, geo.height() - dy)
            geo.setTop(geo.bottom() - new_h)
        if self._resize_edge & _ResizeEdge.BOTTOM:
            geo.setHeight(max(min_h, geo.height() + dy))

        self.setGeometry(geo)
