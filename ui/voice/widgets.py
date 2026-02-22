"""
Voice Dashboard widgets — PySide6 panels mirroring the web voice dashboard.

Each widget receives a ``data: dict`` snapshot from VoiceEnginePoller
and renders the relevant section.  Dark theme matches the web UI palette.
"""

from __future__ import annotations

import math
import time
from typing import Any

from PySide6.QtCore import QRectF, Qt, QTimer, Slot
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# Colour palette (matches web dashboard CSS vars)
# ---------------------------------------------------------------------------

BG_PRIMARY = "#0a0a0f"
BG_CARD = "#151520"
BG_CARD_HOVER = "#1a1a28"
BG_INPUT = "#12121c"
BORDER = "#1e1e30"
BORDER_LIGHT = "#2a2a40"
TEXT_PRIMARY = "#e4e4ed"
TEXT_SECONDARY = "#8888a0"
TEXT_MUTED = "#555570"
ACCENT = "#7c5cfc"
ACCENT_LIGHT = "#a78bfa"
GREEN = "#34d399"
RED = "#f87171"
YELLOW = "#fbbf24"
BLUE = "#60a5fa"
CYAN = "#22d3ee"

_MONO = QFont("JetBrains Mono", 10)
_MONO.setStyleHint(QFont.StyleHint.Monospace)

_TITLE_FONT = QFont("Inter", 9)
_TITLE_FONT.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)

_STATE_COLORS: dict[str, str] = {
    "IDLE": GREEN,
    "LISTENING": BLUE,
    "BACKCHANNELING": CYAN,
    "PROCESSING": YELLOW,
    "FILLING": YELLOW,
    "SPEAKING": ACCENT,
    "INTERRUPTED": RED,
    "ONBOARDING": ACCENT_LIGHT,
    "N/A": TEXT_MUTED,
}


def _card_frame(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    """Create a dark card frame with optional title label."""
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; "
        f"border-radius: 10px; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(6)
    if title:
        lbl = QLabel(title.upper())
        lbl.setFont(_TITLE_FONT)
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 10px; "
            f"letter-spacing: 1.2px; border: none;"
        )
        layout.addWidget(lbl)
    return frame, layout


def _value_label(text: str = "", color: str = TEXT_PRIMARY, size: int = 22) -> QLabel:
    """Big value label used in status cards."""
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-size: {size}px; font-weight: bold; border: none;"
    )
    return lbl


def _detail_label(text: str = "", color: str = TEXT_SECONDARY) -> QLabel:
    """Small detail / subtitle label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {color}; font-size: 11px; border: none;")
    return lbl


# ========================================================================
# HeroWidget — state orb, FSM label, mode, duration, buttons
# ========================================================================

class HeroWidget(QWidget):
    """Large hero card showing the current voice engine state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        frame, layout = _card_frame()

        row = QHBoxLayout()
        row.setSpacing(20)

        self._orb = _StateOrb()
        self._orb.setFixedSize(80, 80)
        row.addWidget(self._orb)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._state_label = _value_label("IDLE", GREEN, 28)
        self._mode_label = _detail_label("Voice Engine")
        self._duration_label = _detail_label("0.0s")
        info.addWidget(self._state_label)
        info.addWidget(self._mode_label)
        info.addWidget(self._duration_label)
        info.addStretch()
        row.addLayout(info, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(8)
        self._tts_btn = QPushButton("Test TTS")
        self._tts_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: white; border: none; "
            f"border-radius: 6px; padding: 8px 16px; font-weight: bold; }} "
            f"QPushButton:hover {{ background: {ACCENT_LIGHT}; }}"
        )
        btn_col.addWidget(self._tts_btn)
        btn_col.addStretch()
        row.addLayout(btn_col)

        layout.addLayout(row)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update hero card from poller snapshot."""
        state = data.get("fsm_state", "N/A")
        color = _STATE_COLORS.get(state, TEXT_MUTED)
        self._state_label.setText(state)
        self._state_label.setStyleSheet(
            f"color: {color}; font-size: 28px; font-weight: bold; border: none;"
        )
        self._orb.set_color(color)

        running = data.get("running", False)
        mode = "Full-Duplex Engine" if data.get("engine_available") else "Not Available"
        status = "Active" if running else "Stopped"
        status_color = GREEN if running else RED
        self._mode_label.setText(
            f'{mode} <span style="color:{status_color}">• {status}</span>'
        )

        dur = data.get("state_duration_s", 0.0)
        self._duration_label.setText(f"State duration: {dur:.1f}s")


class _StateOrb(QWidget):
    """Glowing circle indicating the current FSM state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(GREEN)

    def set_color(self, hex_color: str) -> None:
        """Set the orb color and repaint."""
        self._color = QColor(hex_color)
        self.update()

    def paintEvent(self, event: Any) -> None:
        """Draw a radial-gradient orb with glow."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy, r = w / 2, h / 2, min(w, h) / 2 - 4

        glow = QRadialGradient(cx, cy, r * 1.5)
        c = QColor(self._color)
        c.setAlpha(60)
        glow.setColorAt(0, c)
        c.setAlpha(0)
        glow.setColorAt(1, c)
        p.setBrush(QBrush(glow))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r * 1.3, cy - r * 1.3, r * 2.6, r * 2.6))

        grad = QRadialGradient(cx - r * 0.3, cy - r * 0.3, r * 1.2)
        light = QColor(self._color).lighter(150)
        grad.setColorAt(0, light)
        grad.setColorAt(1, self._color)
        p.setBrush(QBrush(grad))
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
        p.end()


# ========================================================================
# StatusCardsWidget — TTS, STT, Wake Word, Speakers
# ========================================================================

class StatusCardsWidget(QWidget):
    """Four status cards in a horizontal row."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self._tts_val, self._tts_det, c1 = self._make_card("TTS ENGINE")
        self._stt_val, self._stt_det, c2 = self._make_card("STT ENGINE")
        self._wake_val, self._wake_det, c3 = self._make_card("WAKE WORD")
        self._spk_val, self._spk_det, c4 = self._make_card("SPEAKERS")

        for c in (c1, c2, c3, c4):
            row.addWidget(c, 1)

    def _make_card(self, title: str) -> tuple[QLabel, QLabel, QFrame]:
        """Build a single status card."""
        frame, layout = _card_frame(title)
        val = _value_label("N/A", TEXT_MUTED)
        det = _detail_label("")
        layout.addWidget(val)
        layout.addWidget(det)
        return val, det, frame

    def update(self, data: dict[str, Any]) -> None:
        """Update all four cards."""
        if data.get("tts_available"):
            self._tts_val.setText("READY")
            self._tts_val.setStyleSheet(
                f"color: {GREEN}; font-size: 22px; font-weight: bold; border: none;"
            )
            self._tts_det.setText(f"Provider: {data.get('tts_provider', 'unknown')}")
        else:
            self._tts_val.setText("N/A")
            self._tts_val.setStyleSheet(
                f"color: {YELLOW}; font-size: 22px; font-weight: bold; border: none;"
            )

        if data.get("stt_available"):
            self._stt_val.setText("READY")
            self._stt_val.setStyleSheet(
                f"color: {GREEN}; font-size: 22px; font-weight: bold; border: none;"
            )
            self._stt_det.setText(f"Model: {data.get('stt_model', 'whisper')}")
        else:
            self._stt_val.setText("N/A")
            self._stt_val.setStyleSheet(
                f"color: {YELLOW}; font-size: 22px; font-weight: bold; border: none;"
            )

        self._wake_val.setText("OFF")
        self._wake_val.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 22px; font-weight: bold; border: none;"
        )

        total = data.get("speakers", {}).get("total_tracked", 0)
        self._spk_val.setText(str(total))
        self._spk_val.setStyleSheet(
            f"color: {CYAN}; font-size: 22px; font-weight: bold; border: none;"
        )
        self._spk_det.setText("Tracked")


# ========================================================================
# AudioLevelsWidget — waveform canvas + SNR badge
# ========================================================================

class AudioLevelsWidget(QWidget):
    """Real-time mic level meter with dB scale, SNR badge, and mic test."""

    _MAX_SAMPLES = 200

    mic_test_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[float] = [0.0] * self._MAX_SAMPLES
        self.setMinimumHeight(80)
        self.setMaximumHeight(120)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame()

        header = QHBoxLayout()
        header.addWidget(_detail_label("AUDIO LEVELS"))
        self._db_label = QLabel("-- dB")
        self._db_label.setStyleSheet(
            f"color: {GREEN}; font-weight: bold; font-size: 11px; border: none;"
        )
        header.addWidget(self._db_label)
        self._snr_badge = QLabel("SNR: -- dB")
        self._snr_badge.setStyleSheet(
            f"background: {BORDER_LIGHT}; color: {GREEN}; "
            f"border-radius: 4px; padding: 2px 8px; font-size: 10px;"
        )
        header.addStretch()
        header.addWidget(self._snr_badge)

        self._mic_test_btn = QPushButton("Test Mic")
        self._mic_test_btn.setStyleSheet(
            f"QPushButton {{ background: {BORDER_LIGHT}; color: {TEXT_SECONDARY}; "
            f"border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px; "
            f"font-weight: bold; }} "
            f"QPushButton:hover {{ background: {BORDER}; color: {TEXT_PRIMARY}; }}"
        )
        self._mic_test_btn.clicked.connect(self.mic_test_requested.emit)
        header.addWidget(self._mic_test_btn)

        self._mic_test_status = QLabel("")
        self._mic_test_status.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none;"
        )
        header.addWidget(self._mic_test_status)
        layout.addLayout(header)

        self._level_bar = QProgressBar()
        self._level_bar.setRange(0, 100)
        self._level_bar.setValue(0)
        self._level_bar.setTextVisible(False)
        self._level_bar.setFixedHeight(14)
        self._level_bar.setStyleSheet(
            f"QProgressBar {{ background: {BG_INPUT}; border: 1px solid {BORDER}; "
            f"border-radius: 6px; }} "
            f"QProgressBar::chunk {{ background: {GREEN}; border-radius: 6px; }}"
        )
        layout.addWidget(self._level_bar)

        self._canvas = _WaveformCanvas()
        self._canvas.setMinimumHeight(30)
        layout.addWidget(self._canvas)
        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update level bar and waveform from real mic RMS."""
        mic_level = data.get("mic_level", 0.0)
        self._canvas.push_sample(min(mic_level * 5.0, 1.0))

        if mic_level > 0:
            db = 20 * math.log10(max(mic_level, 1e-10))
        else:
            db = -80.0

        db_clamped = max(-60.0, min(0.0, db))
        pct = int((db_clamped + 60.0) / 60.0 * 100)
        self._level_bar.setValue(pct)
        self._db_label.setText(f"{db:.1f} dB")

        if pct > 85:
            bar_color = RED
            label_color = RED
        elif pct > 60:
            bar_color = YELLOW
            label_color = YELLOW
        else:
            bar_color = GREEN
            label_color = GREEN

        self._level_bar.setStyleSheet(
            f"QProgressBar {{ background: {BG_INPUT}; border: 1px solid {BORDER}; "
            f"border-radius: 6px; }} "
            f"QProgressBar::chunk {{ background: {bar_color}; border-radius: 6px; }}"
        )
        self._db_label.setStyleSheet(
            f"color: {label_color}; font-weight: bold; font-size: 11px; border: none;"
        )

        snr = data.get("snr_db")
        if snr is not None:
            self._snr_badge.setText(f"SNR: {snr:.0f} dB")
        else:
            self._snr_badge.setText("SNR: -- dB")

    def show_mic_test_result(self, passed: bool, peak_db: float) -> None:
        """Display mic test pass/fail result."""
        if passed:
            self._mic_test_status.setText(f"PASS ({peak_db:.1f} dB)")
            self._mic_test_status.setStyleSheet(
                f"color: {GREEN}; font-size: 10px; font-weight: bold; border: none;"
            )
        else:
            self._mic_test_status.setText(f"FAIL ({peak_db:.1f} dB)")
            self._mic_test_status.setStyleSheet(
                f"color: {RED}; font-size: 10px; font-weight: bold; border: none;"
            )
        self._mic_test_btn.setEnabled(True)

    def show_mic_test_recording(self) -> None:
        """Show recording state on the mic test button."""
        self._mic_test_btn.setEnabled(False)
        self._mic_test_status.setText("Recording 3s...")
        self._mic_test_status.setStyleSheet(
            f"color: {YELLOW}; font-size: 10px; font-weight: bold; border: none;"
        )


class _WaveformCanvas(QWidget):
    """Custom QPainter waveform."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._samples: list[float] = [0.0] * 200
        self.setStyleSheet(f"background: {BG_PRIMARY}; border: 1px solid {BORDER};")

    def push_sample(self, value: float) -> None:
        """Add a sample and trigger repaint."""
        self._samples.append(max(-1.0, min(1.0, value)))
        if len(self._samples) > 200:
            self._samples.pop(0)
        self.update()

    def paintEvent(self, event: Any) -> None:
        """Draw the waveform."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h / 2

        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(0, int(mid_y), w, int(mid_y))

        if len(self._samples) < 2:
            p.end()
            return

        pen = QPen(QColor(BLUE), 1.5)
        p.setPen(pen)
        step = w / max(len(self._samples) - 1, 1)
        path = QPainterPath()
        path.moveTo(0, mid_y - self._samples[0] * mid_y * 0.8)
        for i, s in enumerate(self._samples[1:], 1):
            path.lineTo(i * step, mid_y - s * mid_y * 0.8)
        p.drawPath(path)
        p.end()


# ========================================================================
# TranscriptWidget — live conversation transcript
# ========================================================================

class TranscriptWidget(QWidget):
    """Scrolling live transcript with user/emily entries."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame()

        header = QHBoxLayout()
        header.addWidget(_detail_label("LIVE TRANSCRIPT"))
        self._count_label = _detail_label("0 entries")
        header.addWidget(self._count_label)
        header.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {BORDER_LIGHT}; color: {TEXT_SECONDARY}; "
            f"border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px; }} "
            f"QPushButton:hover {{ background: {BORDER}; }}"
        )
        clear_btn.clicked.connect(self._clear)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(_MONO)
        self._text.setStyleSheet(
            f"QTextEdit {{ background: {BG_INPUT}; color: {TEXT_PRIMARY}; "
            f"border: 1px solid {BORDER}; border-radius: 6px; padding: 8px; }}"
        )
        layout.addWidget(self._text, 1)
        self._entry_count = 0

        self._empty_label = QLabel("Waiting for voice activity...")
        self._empty_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; border: none;"
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

        outer.addWidget(frame)

    def add_entry(self, role: str, text: str) -> None:
        """Add a transcript entry."""
        self._empty_label.hide()
        self._entry_count += 1
        self._count_label.setText(f"{self._entry_count} entries")

        ts = time.strftime("%H:%M:%S")
        if role == "user":
            color = BLUE
            border_color = BLUE
        else:
            color = ACCENT_LIGHT
            border_color = ACCENT

        html = (
            f'<div style="border-left: 3px solid {border_color}; '
            f'padding: 4px 8px; margin: 4px 0;">'
            f'<span style="color:{TEXT_MUTED};font-size:10px">{ts}</span> '
            f'<span style="color:{color};font-weight:bold">{role.upper()}</span><br>'
            f'<span style="color:{TEXT_PRIMARY}">{text}</span></div>'
        )
        self._text.append(html)
        self._text.moveCursor(self._text.textCursor().MoveOperation.End)

    def _clear(self) -> None:
        """Clear the transcript."""
        self._text.clear()
        self._entry_count = 0
        self._count_label.setText("0 entries")
        self._empty_label.show()


# ========================================================================
# PipelineWidget — module status chips
# ========================================================================

class PipelineWidget(QWidget):
    """Grid of pipeline module status chips."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self._frame, self._layout = _card_frame("PIPELINE MODULES")
        self._count_badge = QLabel("0 loaded")
        self._count_badge.setStyleSheet(
            f"background: {ACCENT}; color: white; border-radius: 8px; "
            f"padding: 2px 10px; font-size: 10px; font-weight: bold;"
        )
        self._layout.insertWidget(0, self._count_badge, 0, Qt.AlignmentFlag.AlignRight)

        self._grid = QGridLayout()
        self._grid.setSpacing(8)
        self._layout.addLayout(self._grid)
        self._chips: dict[str, QLabel] = {}
        outer.addWidget(self._frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update module chips in-place (no deleteLater to avoid PySide6 crash)."""
        modules = data.get("pipeline_modules", {})
        loaded_count = sum(1 for m in modules.values() if m.get("loaded"))
        self._count_badge.setText(f"{loaded_count} loaded")

        col = 0
        row = 0
        for name, info in modules.items():
            loaded = info.get("loaded", False)
            dot_color = GREEN if loaded else RED
            detail = self._module_detail(name, info)
            html = (
                f'<span style="color:{dot_color}">●</span> '
                f'<span style="color:{TEXT_PRIMARY}">{name}</span>'
                f'<br><span style="color:{TEXT_MUTED};font-size:9px">{detail}</span>'
            )

            if name in self._chips:
                self._chips[name].setText(html)
            else:
                chip = QLabel(html)
                chip.setStyleSheet(
                    f"background: {BG_INPUT}; border: 1px solid {BORDER}; "
                    f"border-radius: 6px; padding: 6px 10px; font-size: 11px;"
                )
                self._grid.addWidget(chip, row, col)
                self._chips[name] = chip

            col += 1
            if col >= 3:
                col = 0
                row += 1

    def _module_detail(self, name: str, info: dict[str, Any]) -> str:
        """Format module-specific detail text."""
        if name == "audio_capture":
            r = info.get("input_rate")
            return f"{r} Hz" if r else ""
        if name == "aec":
            return f"tail {info.get('tail_ms', '?')}ms"
        if name == "noise_suppress":
            return f"SNR {info.get('snr_db', '--')} dB"
        if name == "streaming_stt":
            return info.get("model", "") or ""
        if name == "speaker_engine":
            return f"{info.get('active_count', 0)}/{info.get('max_speakers', '?')}"
        return ""


# ========================================================================
# EmotionWidget — primary emotion + progress bars
# ========================================================================

class EmotionWidget(QWidget):
    """Displays detected user emotion with dimension bars."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("USER EMOTION")

        self._primary = _value_label("--", TEXT_MUTED, 18)
        self._confidence = _detail_label("Confidence: --")
        layout.addWidget(self._primary)
        layout.addWidget(self._confidence)

        self._bars: dict[str, QProgressBar] = {}
        for name, color in [
            ("Valence", GREEN),
            ("Arousal", YELLOW),
            ("Engagement", BLUE),
            ("Cognitive Load", RED),
        ]:
            lbl = _detail_label(name)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setStyleSheet(
                f"QProgressBar {{ background: {BG_INPUT}; border: none; border-radius: 4px; }} "
                f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}"
            )
            layout.addWidget(lbl)
            layout.addWidget(bar)
            self._bars[name.lower().replace(" ", "_")] = bar

        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update emotion display."""
        emotion = data.get("emotion")
        if emotion is None:
            self._primary.setText("--")
            self._confidence.setText("Confidence: --")
            for bar in self._bars.values():
                bar.setValue(0)
            return

        primary = emotion.get("primary")
        self._primary.setText(
            str(primary.value if hasattr(primary, "value") else primary or "--")
        )
        self._primary.setStyleSheet(
            f"color: {ACCENT_LIGHT}; font-size: 18px; font-weight: bold; border: none;"
        )
        conf = emotion.get("confidence", 0)
        self._confidence.setText(f"Confidence: {conf:.0%}")

        self._bars["valence"].setValue(int(emotion.get("valence", 0) * 100))
        self._bars["arousal"].setValue(int(emotion.get("arousal", 0) * 100))
        self._bars["engagement"].setValue(int(emotion.get("engagement", 0) * 100))
        self._bars["cognitive_load"].setValue(
            int(emotion.get("cognitive_load", 0) * 100)
        )


# ========================================================================
# TurnDetectionWidget — action, score, confidence breakdown
# ========================================================================

class TurnDetectionWidget(QWidget):
    """Shows the latest turn detection signal and breakdown."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("TURN DETECTION")

        self._action = _value_label("--", TEXT_MUTED, 18)
        self._score = _detail_label("Score: --")
        layout.addWidget(self._action)
        layout.addWidget(self._score)

        self._breakdown_text = QTextEdit()
        self._breakdown_text.setReadOnly(True)
        self._breakdown_text.setFont(_MONO)
        self._breakdown_text.setMaximumHeight(100)
        self._breakdown_text.setStyleSheet(
            f"QTextEdit {{ background: {BG_INPUT}; color: {TEXT_SECONDARY}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; padding: 4px; "
            f"font-size: 10px; }}"
        )
        layout.addWidget(self._breakdown_text)
        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update turn detection display."""
        ts = data.get("turn_signal")
        if ts is None:
            self._action.setText("--")
            self._score.setText("Score: --")
            self._breakdown_text.clear()
            return

        action = ts.get("action")
        action_str = action.name if hasattr(action, "name") else str(action or "--")
        self._action.setText(action_str)
        self._action.setStyleSheet(
            f"color: {CYAN}; font-size: 18px; font-weight: bold; border: none;"
        )
        self._score.setText(f"Score: {ts.get('score', 0):.3f}")

        breakdown = ts.get("breakdown", {})
        lines = [f"{k}: {v:.3f}" for k, v in breakdown.items()]
        self._breakdown_text.setPlainText("\n".join(lines))


# ========================================================================
# RhythmWidget — user/emily rhythm + entrainment gauge
# ========================================================================

class RhythmWidget(QWidget):
    """Rhythm synchronization display with an entrainment ring gauge."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("RHYTHM SYNC")

        row = QHBoxLayout()

        left = QVBoxLayout()
        self._user_rate = _detail_label("User rate: -- syl/s")
        self._emily_rate = _detail_label("Emily rate: -- syl/s")
        self._user_pause = _detail_label("Pause: -- ms")
        self._emily_phrase = _detail_label("Phrase: -- words")
        self._latency = _detail_label("Latency: -- ms")
        for w in (
            self._user_rate,
            self._emily_rate,
            self._user_pause,
            self._emily_phrase,
            self._latency,
        ):
            left.addWidget(w)
        left.addStretch()
        row.addLayout(left, 1)

        self._gauge = _EntrainmentGauge()
        self._gauge.setFixedSize(90, 90)
        row.addWidget(self._gauge)

        layout.addLayout(row)
        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update rhythm display."""
        rhythm = data.get("rhythm")
        if rhythm is None:
            return
        u = rhythm.get("user", {})
        e = rhythm.get("emily", {})
        self._user_rate.setText(f"User rate: {u.get('speaking_rate', 0):.1f} syl/s")
        self._emily_rate.setText(f"Emily rate: {e.get('speaking_rate', 0):.1f} syl/s")
        self._user_pause.setText(f"Pause: {u.get('pause_ms', 0):.0f} ms")
        self._emily_phrase.setText(f"Phrase: {e.get('phrase_words', 0)} words")
        self._latency.setText(f"Latency: {u.get('latency_ms', 0):.0f} ms")
        self._gauge.set_value(rhythm.get("entrainment", 0.0))


class _EntrainmentGauge(QWidget):
    """Ring-arc gauge showing entrainment degree 0–1."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0

    def set_value(self, v: float) -> None:
        """Set gauge value (0.0 to 1.0)."""
        self._value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, event: Any) -> None:
        """Draw the ring gauge."""
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = min(self.width(), self.height())
        rect = QRectF(4, 4, s - 8, s - 8)

        p.setPen(QPen(QColor(BORDER_LIGHT), 6))
        p.drawArc(rect, 225 * 16, -270 * 16)

        p.setPen(QPen(QColor(ACCENT), 6))
        span = int(-270 * 16 * self._value)
        p.drawArc(rect, 225 * 16, span)

        p.setPen(QColor(TEXT_PRIMARY))
        p.setFont(QFont("Inter", 14, QFont.Weight.Bold))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._value:.0%}")
        p.end()


# ========================================================================
# SessionStatsWidget — sidebar stats
# ========================================================================

class SessionStatsWidget(QWidget):
    """Session statistics panel for the sidebar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("SESSION STATS")

        self._rows: dict[str, QLabel] = {}
        for key in (
            "Backchannels",
            "Interrupts",
            "Transcript Turns",
            "Session Time",
        ):
            row = QHBoxLayout()
            lbl = _detail_label(key)
            val = QLabel("0")
            val.setStyleSheet(
                f"color: {TEXT_PRIMARY}; font-weight: bold; font-size: 13px; border: none;"
            )
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            layout.addLayout(row)
            self._rows[key] = val

        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update stat values."""
        stats = data.get("stats", {})
        self._rows["Backchannels"].setText(str(stats.get("backchannels", 0)))
        self._rows["Interrupts"].setText(str(stats.get("interrupts", 0)))

        uptime = data.get("uptime_s", 0)
        m, s = divmod(int(uptime), 60)
        h, m = divmod(m, 60)
        self._rows["Session Time"].setText(f"{h}:{m:02d}:{s:02d}")


# ========================================================================
# SpeakersWidget — active speakers list
# ========================================================================

class SpeakersWidget(QWidget):
    """Active speakers panel for the sidebar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("ACTIVE SPEAKERS")
        self._list_layout = QVBoxLayout()
        self._list_layout.setSpacing(4)
        layout.addLayout(self._list_layout)
        self._empty = _detail_label("No speakers detected")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._list_layout.addWidget(self._empty)
        self._speaker_labels: list[QLabel] = []
        outer.addWidget(frame)

    def update(self, data: dict[str, Any]) -> None:
        """Update speaker list in-place (no deleteLater to avoid PySide6 crash)."""
        speakers = data.get("speakers", {}).get("list", [])

        if not speakers:
            self._empty.show()
            for lbl in self._speaker_labels:
                lbl.hide()
            return

        self._empty.hide()

        while len(self._speaker_labels) < len(speakers):
            lbl = QLabel(self)
            lbl.setStyleSheet(
                f"padding: 4px 8px; border-bottom: 1px solid {BORDER}; font-size: 12px;"
            )
            self._list_layout.addWidget(lbl)
            self._speaker_labels.append(lbl)

        for i, s in enumerate(speakers):
            label_text = s.get("label") or s.get("id") or "Unknown"
            conf = s.get("confidence", 0)
            primary = s.get("is_primary", False)
            badge = (
                f' <span style="color:{ACCENT};font-size:9px;'
                f'background:{BORDER_LIGHT};border-radius:3px;padding:1px 4px">'
                f"PRIMARY</span>"
                if primary
                else ""
            )
            self._speaker_labels[i].setText(
                f'<span style="color:{TEXT_PRIMARY}">{label_text}</span>'
                f"{badge} "
                f'<span style="color:{TEXT_MUTED};font-size:10px">{conf:.0%}</span>'
            )
            self._speaker_labels[i].show()

        for i in range(len(speakers), len(self._speaker_labels)):
            self._speaker_labels[i].hide()


# ========================================================================
# SystemWidget — CPU / RAM / VRAM
# ========================================================================

class SystemWidget(QWidget):
    """System resource monitoring for the sidebar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("SYSTEM")

        self._cpu_label = _detail_label("CPU: --%")
        self._ram_label = _detail_label("RAM: -- / -- GB")
        self._vram_label = _detail_label("VRAM: -- / -- MB")
        layout.addWidget(self._cpu_label)
        layout.addWidget(self._ram_label)
        layout.addWidget(self._vram_label)

        self._cpu_bar = self._make_bar(BLUE)
        self._ram_bar = self._make_bar(GREEN)
        self._vram_bar = self._make_bar(ACCENT)
        layout.addWidget(self._cpu_bar)
        layout.addWidget(self._ram_bar)
        layout.addWidget(self._vram_bar)

        outer.addWidget(frame)

        self._sys_timer = QTimer(self)
        self._sys_timer.setInterval(5000)
        self._sys_timer.timeout.connect(self._read_system)
        self._sys_timer.start()
        self._read_system()

    def _make_bar(self, color: str) -> QProgressBar:
        """Create a progress bar."""
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            f"QProgressBar {{ background: {BG_INPUT}; border: none; border-radius: 3px; }} "
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )
        return bar

    def _read_system(self) -> None:
        """Read CPU/RAM/VRAM on a timer."""
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            self._cpu_label.setText(f"CPU: {cpu:.0f}%")
            self._cpu_bar.setValue(int(cpu))
            ram_used = mem.used / (1024 ** 3)
            ram_total = mem.total / (1024 ** 3)
            self._ram_label.setText(f"RAM: {ram_used:.1f} / {ram_total:.1f} GB")
            self._ram_bar.setValue(int(mem.percent))
        except ImportError:
            pass

        try:
            import pynvml

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            info = pynvml.nvmlDeviceGetMemoryInfo(handle)
            used_mb = info.used / (1024 ** 2)
            total_mb = info.total / (1024 ** 2)
            pct = int(used_mb / total_mb * 100) if total_mb > 0 else 0
            self._vram_label.setText(f"VRAM: {used_mb:.0f} / {total_mb:.0f} MB")
            self._vram_bar.setValue(pct)
        except Exception:
            self._vram_label.setText("VRAM: N/A")

    def update(self, data: dict[str, Any]) -> None:
        """No-op — system stats are read on their own timer."""


# ========================================================================
# DeviceSelectorWidget — mic / speaker combo boxes
# ========================================================================

_COMBO_STYLE = (
    f"QComboBox {{ background: {BG_INPUT}; color: {TEXT_PRIMARY}; "
    f"border: 1px solid {BORDER_LIGHT}; border-radius: 6px; padding: 5px 8px; "
    f"font-size: 11px; }} "
    f"QComboBox::drop-down {{ border: none; }} "
    f"QComboBox QAbstractItemView {{ background: {BG_CARD}; color: {TEXT_PRIMARY}; "
    f"selection-background-color: {ACCENT}; border: 1px solid {BORDER_LIGHT}; }}"
)

_REFRESH_BTN_STYLE = (
    f"QPushButton {{ background: {BG_INPUT}; color: {TEXT_SECONDARY}; "
    f"border: 1px solid {BORDER_LIGHT}; border-radius: 6px; padding: 4px 10px; "
    f"font-size: 10px; }} "
    f"QPushButton:hover {{ background: {BG_CARD_HOVER}; color: {TEXT_PRIMARY}; }}"
)


class DeviceSelectorWidget(QWidget):
    """Mic and speaker selection dropdowns for the sidebar."""

    device_changed = Signal(str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._populating = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("AUDIO DEVICES")

        mic_label = _detail_label("Microphone")
        layout.addWidget(mic_label)
        self._input_combo = QComboBox()
        self._input_combo.setStyleSheet(_COMBO_STYLE)
        self._input_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._input_combo)

        spk_label = _detail_label("Speaker")
        layout.addWidget(spk_label)
        self._output_combo = QComboBox()
        self._output_combo.setStyleSheet(_COMBO_STYLE)
        self._output_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        layout.addWidget(self._output_combo)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setStyleSheet(_REFRESH_BTN_STYLE)
        refresh_btn.clicked.connect(self.refresh_devices)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        outer.addWidget(frame)

        self._input_combo.currentIndexChanged.connect(self._on_input_changed)
        self._output_combo.currentIndexChanged.connect(self._on_output_changed)

        self.refresh_devices()

    def refresh_devices(self) -> None:
        """Re-scan audio devices and repopulate the combo boxes."""
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
        except ImportError:
            return

        self._populating = True
        try:
            devices = sd.query_devices()
            try:
                default_in, default_out = sd.default.device
            except Exception:
                default_in = default_out = None

            self._input_combo.clear()
            self._output_combo.clear()

            self._input_combo.addItem("System Default", None)
            self._output_combo.addItem("System Default", None)

            for i, dev in enumerate(devices):
                name = dev["name"]
                if dev["max_input_channels"] > 0:
                    suffix = "  (default)" if i == default_in else ""
                    self._input_combo.addItem(f"{name}{suffix}", i)
                if dev["max_output_channels"] > 0:
                    suffix = "  (default)" if i == default_out else ""
                    self._output_combo.addItem(f"{name}{suffix}", i)
        finally:
            self._populating = False

    def _on_input_changed(self, index: int) -> None:
        """Handle microphone combo change."""
        if self._populating or index < 0:
            return
        dev_index = self._input_combo.itemData(index)
        self.device_changed.emit("input", dev_index)

    def _on_output_changed(self, index: int) -> None:
        """Handle speaker combo change."""
        if self._populating or index < 0:
            return
        dev_index = self._output_combo.itemData(index)
        self.device_changed.emit("output", dev_index)

    def select_device(self, device_type: str, device_index: int | None) -> None:
        """Programmatically select a device by index (used by snapshot updates)."""
        combo = self._input_combo if device_type == "input" else self._output_combo
        self._populating = True
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == device_index:
                    combo.setCurrentIndex(i)
                    return
        finally:
            self._populating = False

    def update(self, data: dict[str, Any]) -> None:
        """Sync selection with current engine state."""
        cur_in = data.get("current_input_device")
        cur_out = data.get("current_output_device")
        if cur_in is not None:
            self.select_device("input", cur_in)
        if cur_out is not None:
            self.select_device("output", cur_out)


# ========================================================================
# VoiceDebugWidget — full STT, TTS, and conversation log
# ========================================================================

class VoiceDebugWidget(QWidget):
    """Tabbed debug panel showing STT events, TTS events, and full conversation."""

    _MAX_LOG_LINES = 500

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame, layout = _card_frame("VOICE DEBUG")

        tab_row = QHBoxLayout()
        self._tabs: dict[str, QPushButton] = {}
        for tab_name in ("STT", "TTS", "Conversation"):
            btn = QPushButton(tab_name)
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton {{ background: {BG_INPUT}; color: {TEXT_SECONDARY}; "
                f"border: 1px solid {BORDER}; border-radius: 4px; "
                f"padding: 4px 14px; font-size: 11px; font-weight: bold; }} "
                f"QPushButton:checked {{ background: {ACCENT}; color: white; border: none; }}"
            )
            btn.clicked.connect(lambda checked, n=tab_name: self._switch_tab(n))
            tab_row.addWidget(btn)
            self._tabs[tab_name] = btn
        tab_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {BORDER_LIGHT}; color: {TEXT_SECONDARY}; "
            f"border: none; border-radius: 4px; padding: 4px 12px; font-size: 11px; }} "
            f"QPushButton:hover {{ background: {BORDER}; }}"
        )
        clear_btn.clicked.connect(self._clear_all)
        tab_row.addWidget(clear_btn)
        layout.addLayout(tab_row)

        self._stt_log = QTextEdit()
        self._tts_log = QTextEdit()
        self._conv_log = QTextEdit()
        for log_widget in (self._stt_log, self._tts_log, self._conv_log):
            log_widget.setReadOnly(True)
            log_widget.setFont(_MONO)
            log_widget.setStyleSheet(
                f"QTextEdit {{ background: {BG_INPUT}; color: {TEXT_PRIMARY}; "
                f"border: 1px solid {BORDER}; border-radius: 6px; padding: 8px; }}"
            )
            layout.addWidget(log_widget)

        self._tts_log.hide()
        self._conv_log.hide()
        self._active_tab = "STT"
        self._tabs["STT"].setChecked(True)

        self._stt_count = 0
        self._tts_count = 0
        self._conv_count = 0

        self._partial_label = QLabel("")
        self._partial_label.setStyleSheet(
            f"background: {BG_INPUT}; color: {YELLOW}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; "
            f"padding: 4px 8px; font-size: 11px;"
        )
        self._partial_label.setFont(_MONO)
        self._partial_label.setWordWrap(True)
        layout.addWidget(self._partial_label)

        outer.addWidget(frame)

    def _switch_tab(self, name: str) -> None:
        """Switch visible log pane."""
        self._active_tab = name
        for tab_name, btn in self._tabs.items():
            btn.setChecked(tab_name == name)
        self._stt_log.setVisible(name == "STT")
        self._tts_log.setVisible(name == "TTS")
        self._conv_log.setVisible(name == "Conversation")

    def _clear_all(self) -> None:
        """Clear all three log panes."""
        self._stt_log.clear()
        self._tts_log.clear()
        self._conv_log.clear()
        self._stt_count = 0
        self._tts_count = 0
        self._conv_count = 0

    def _trim_log(self, widget: QTextEdit) -> None:
        """Keep log widget from growing unbounded."""
        doc = widget.document()
        if doc is not None and doc.blockCount() > self._MAX_LOG_LINES:
            cursor = widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.movePosition(
                cursor.MoveOperation.Down,
                cursor.MoveMode.KeepAnchor,
                doc.blockCount() - self._MAX_LOG_LINES,
            )
            cursor.removeSelectedText()

    def update(self, data: dict[str, Any]) -> None:
        """Update live STT partial and FSM state from poller snapshot."""
        partial = data.get("stt_partial", "")
        fsm_state = data.get("fsm_state", "N/A")
        mic_db = data.get("mic_level", 0.0)
        if mic_db > 0:
            import math as _math
            db_val = 20 * _math.log10(max(mic_db, 1e-10))
        else:
            db_val = -80.0

        if partial.strip():
            self._partial_label.setText(
                f'<span style="color:{TEXT_MUTED}">FSM: {fsm_state} | '
                f'Mic: {db_val:.0f}dB</span>  '
                f'<span style="color:{YELLOW}">STT hearing:</span> '
                f'<span style="color:{TEXT_PRIMARY}">{partial}</span>'
            )
        else:
            self._partial_label.setText(
                f'<span style="color:{TEXT_MUTED}">FSM: {fsm_state} | '
                f'Mic: {db_val:.0f}dB | STT: (silence)</span>'
            )

    @Slot(dict)
    def on_fsm(self, event: dict[str, Any]) -> None:
        """Handle FSM state changes — log to STT tab for visibility."""
        ts = time.strftime("%H:%M:%S", time.localtime(event.get("ts", time.time())))
        etype = event.get("kind", "")
        data = event.get("data", {})

        if etype == "state_change":
            old = data.get("old", "?")
            new = data.get("new", "?")
            color = _STATE_COLORS.get(new, TEXT_MUTED)
            self._stt_log.append(
                f'<span style="color:{TEXT_MUTED}">{ts}</span> '
                f'<span style="color:{color}">FSM</span> '
                f'<span style="color:{TEXT_SECONDARY}">{old} → {new}</span>'
            )
            self._trim_log(self._stt_log)

        elif etype == "silence_watchdog":
            prompt = data.get("prompt", "")
            num = data.get("prompt_num", 0)
            self._stt_log.append(
                f'<span style="color:{TEXT_MUTED}">{ts}</span> '
                f'<span style="color:{YELLOW}">SILENCE #{num}</span> '
                f'<span style="color:{TEXT_SECONDARY}">{prompt[:60]}</span>'
            )
            self._trim_log(self._stt_log)

    @Slot(dict)
    def on_perception(self, event: dict[str, Any]) -> None:
        """Handle perception events (STT committed, TTS speaking, Emily spoke)."""
        ts = time.strftime("%H:%M:%S", time.localtime(event.get("ts", time.time())))
        etype = event.get("kind", event.get("type", ""))
        data = event.get("data", {})

        if etype == "stt_committed":
            text = data.get("text", "")
            wc = len(text.split())
            latency = data.get("latency_ms", "")
            latency_str = f"  latency={latency}ms" if latency else ""
            self._stt_count += 1
            self._stt_log.append(
                f'<span style="color:{TEXT_MUTED}">{ts}</span> '
                f'<span style="color:{GREEN}">COMMITTED</span> '
                f'<span style="color:{TEXT_PRIMARY}">{text}</span> '
                f'<span style="color:{TEXT_MUTED}">({wc}w{latency_str})</span>'
            )
            self._trim_log(self._stt_log)

            self._conv_count += 1
            self._conv_log.append(
                f'<div style="border-left: 3px solid {BLUE}; padding: 2px 8px; margin: 2px 0;">'
                f'<span style="color:{TEXT_MUTED};font-size:10px">{ts}</span> '
                f'<span style="color:{BLUE};font-weight:bold">USER</span><br>'
                f'<span style="color:{TEXT_PRIMARY}">{text}</span></div>'
            )
            self._trim_log(self._conv_log)

        elif etype == "tts_speaking":
            text = data.get("text", "")
            preview = text[:80] + ("..." if len(text) > 80 else "")
            engine = data.get("engine", "")
            latency = data.get("first_chunk_ms", "")
            latency_str = f"  first_chunk={latency}ms" if latency else ""
            engine_str = f"  engine={engine}" if engine else ""
            self._tts_count += 1
            self._tts_log.append(
                f'<span style="color:{TEXT_MUTED}">{ts}</span> '
                f'<span style="color:{ACCENT_LIGHT}">TTS</span> '
                f'<span style="color:{TEXT_PRIMARY}">{preview}</span> '
                f'<span style="color:{TEXT_MUTED}">({len(text)}ch{engine_str}{latency_str})</span>'
            )
            self._trim_log(self._tts_log)

        elif etype == "emily_spoke":
            text = data.get("text", "")
            if text:
                self._conv_count += 1
                self._conv_log.append(
                    f'<div style="border-left: 3px solid {ACCENT}; padding: 2px 8px; margin: 2px 0;">'
                    f'<span style="color:{TEXT_MUTED};font-size:10px">{ts}</span> '
                    f'<span style="color:{ACCENT_LIGHT};font-weight:bold">EMILY</span><br>'
                    f'<span style="color:{TEXT_PRIMARY}">{text}</span></div>'
                )
                self._trim_log(self._conv_log)

    @Slot(dict)
    def on_llm(self, event: dict[str, Any]) -> None:
        """Handle LLM events for supplementary TTS/routing info."""
        ts = time.strftime("%H:%M:%S", time.localtime(event.get("ts", time.time())))
        etype = event.get("kind", "")
        data = event.get("data", {})

        if etype == "request":
            model = data.get("model", "")
            tier = data.get("tier", "")
            self._tts_log.append(
                f'<span style="color:{TEXT_MUTED}">{ts}</span> '
                f'<span style="color:{YELLOW}">LLM→</span> '
                f'<span style="color:{TEXT_SECONDARY}">model={model} tier={tier}</span>'
            )
            self._trim_log(self._tts_log)

        elif etype == "response":
            latency = data.get("latency_ms", "")
            content_len = data.get("content_len", "")
            self._tts_log.append(
                f'<span style="color:{TEXT_MUTED}">{ts}</span> '
                f'<span style="color:{CYAN}">LLM←</span> '
                f'<span style="color:{TEXT_SECONDARY}">{content_len}ch in {latency}ms</span>'
            )
            self._trim_log(self._tts_log)
