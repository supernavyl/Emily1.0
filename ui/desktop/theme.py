"""Dark theme stylesheet for Emily Desktop."""

# Colors
BG_PRIMARY = "#0d1117"
BG_SECONDARY = "#161b22"
BG_TERTIARY = "#21262d"
BG_INPUT = "#0d1117"
BORDER = "#30363d"
BORDER_ACTIVE = "#58a6ff"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#484f58"
ACCENT = "#58a6ff"
ACCENT_HOVER = "#79c0ff"
USER_BUBBLE = "#1a3a5c"
EMILY_BUBBLE = "#1c2333"
THINKING_BG = "#1a1e2e"
THINKING_BORDER = "#7c3aed"
ERROR_TEXT = "#f85149"
SUCCESS = "#3fb950"
WARNING = "#d29922"

STYLESHEET = f"""
QMainWindow {{
    background-color: {BG_PRIMARY};
}}

/* Navigation bar */
#navBar {{
    background-color: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
}}

#navBar QPushButton {{
    background: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
}}

#navBar QPushButton:hover {{
    color: {TEXT_PRIMARY};
    background-color: {BG_TERTIARY};
}}

#navBar QPushButton:checked {{
    color: {ACCENT};
    border-bottom: 2px solid {ACCENT};
}}

#navLogo {{
    color: {ACCENT};
    font-size: 16px;
    font-weight: 800;
    padding: 0 16px 0 12px;
}}

/* Sidebar */
#sidebar {{
    background-color: {BG_SECONDARY};
    border-right: 1px solid {BORDER};
}}

#sidebar QPushButton {{
    background: transparent;
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
    text-align: left;
    font-size: 13px;
}}

#sidebar QPushButton:hover {{
    background-color: {BG_TERTIARY};
}}

#sidebar QPushButton:checked {{
    background-color: {BG_TERTIARY};
    color: {ACCENT};
}}

#newChatBtn {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
}}

#newChatBtn:hover {{
    border-color: {ACCENT};
    color: {ACCENT};
}}

/* Top bar */
#topBar {{
    background-color: {BG_SECONDARY};
    border-bottom: 1px solid {BORDER};
    padding: 6px 16px;
}}

#topBar QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}

#topBar QComboBox {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 28px 4px 10px;
    font-size: 12px;
    min-width: 160px;
}}

#topBar QComboBox:hover {{
    border-color: {ACCENT};
}}

#topBar QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

#topBar QComboBox QAbstractItemView {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    selection-background-color: {USER_BUBBLE};
    padding: 4px;
}}

/* Chat area */
#chatScroll {{
    background-color: {BG_PRIMARY};
    border: none;
}}

#chatScroll QScrollBar:vertical {{
    background: transparent;
    width: 8px;
}}

#chatScroll QScrollBar::handle:vertical {{
    background: {BG_TERTIARY};
    border-radius: 4px;
    min-height: 30px;
}}

#chatScroll QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}

#chatScroll QScrollBar::add-line:vertical,
#chatScroll QScrollBar::sub-line:vertical,
#chatScroll QScrollBar::add-page:vertical,
#chatScroll QScrollBar::sub-page:vertical {{
    background: none;
    height: 0;
}}

/* Message bubbles */
.userBubble {{
    background-color: {USER_BUBBLE};
    border-radius: 12px;
    padding: 12px 16px;
    color: {TEXT_PRIMARY};
    font-size: 14px;
}}

.emilyBubble {{
    background-color: {EMILY_BUBBLE};
    border-radius: 12px;
    padding: 12px 16px;
    color: {TEXT_PRIMARY};
    font-size: 14px;
}}

/* Thinking panel */
.thinkingBox {{
    background-color: {THINKING_BG};
    border-left: 3px solid {THINKING_BORDER};
    border-radius: 8px;
    padding: 10px 14px;
    color: {TEXT_SECONDARY};
    font-size: 13px;
    font-style: italic;
}}

/* Input panel */
#inputPanel {{
    background-color: {BG_SECONDARY};
    border-top: 1px solid {BORDER};
    padding: 12px 16px;
}}

#messageInput {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    selection-background-color: {USER_BUBBLE};
}}

#messageInput:focus {{
    border-color: {ACCENT};
}}

#sendBtn {{
    background-color: {ACCENT};
    color: {BG_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 700;
}}

#sendBtn:hover {{
    background-color: {ACCENT_HOVER};
}}

#sendBtn:disabled {{
    background-color: {BG_TERTIARY};
    color: {TEXT_MUTED};
}}

#stopBtn {{
    background-color: {ERROR_TEXT};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 700;
}}

/* Right panel */
#rightPanel {{
    background-color: {BG_SECONDARY};
    border-left: 1px solid {BORDER};
}}

#rightPanel QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}

.statValue {{
    color: {TEXT_PRIMARY};
    font-size: 14px;
    font-weight: 600;
}}

.statLabel {{
    color: {TEXT_SECONDARY};
    font-size: 11px;
}}

.sectionTitle {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
    font-weight: 700;
    padding: 8px 0 4px 0;
}}

/* Generic */
QToolTip {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 6px 10px;
    border-radius: 4px;
    font-size: 12px;
}}

QSplitter::handle {{
    background-color: {BORDER};
    width: 1px;
}}

QSplitter::handle:hover {{
    background-color: {ACCENT};
}}
"""
