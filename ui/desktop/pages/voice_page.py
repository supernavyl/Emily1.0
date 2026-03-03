"""Voice Mode page — live voice conversation controls and transcript."""

from __future__ import annotations

import json

from PySide6.QtCore import QByteArray, Qt, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..widgets import StatRow


class VoicePage(QWidget):
    """Voice mode — mic control, TTS settings, live transcript."""

    def __init__(self, base_url: str = "http://localhost:8000", parent: QWidget | None = None):
        super().__init__(parent)
        self._base_url = base_url
        self._nam = QNetworkAccessManager(self)

        self._build_ui()

        # Poll voice engine status every 3s
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._fetch_status)
        self._poll_timer.start(3000)

        # Poll transcript every 2s
        self._transcript_timer = QTimer(self)
        self._transcript_timer.timeout.connect(self._fetch_transcript)

        # Initial fetch
        QTimer.singleShot(200, self._fetch_status)
        QTimer.singleShot(200, self._fetch_audio_devices)
        QTimer.singleShot(200, self._fetch_voices)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left: controls
        left = QWidget()
        left.setObjectName("sidebar")
        left.setFixedWidth(320)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(12)

        # -- Voice Engine Status --
        left_layout.addWidget(self._section("VOICE ENGINE"))

        self._engine_status = QLabel("Checking...")
        self._engine_status.setStyleSheet(
            f"color: {theme.WARNING}; font-size: 14px; font-weight: 600;"
        )
        left_layout.addWidget(self._engine_status)

        self._engine_state = QLabel("")
        self._engine_state.setStyleSheet(f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
        left_layout.addWidget(self._engine_state)

        left_layout.addSpacing(8)

        # -- Mic control --
        left_layout.addWidget(self._section("MICROPHONE"))

        self._mic_btn = QPushButton("Start Listening")
        self._mic_btn.setObjectName("sendBtn")
        self._mic_btn.setFixedHeight(48)
        self._mic_btn.setCheckable(True)
        self._mic_btn.toggled.connect(self._on_mic_toggle)
        left_layout.addWidget(self._mic_btn)

        self._input_device_combo = QComboBox()
        self._input_device_combo.addItem("Loading devices...")
        left_layout.addWidget(self._input_device_combo)

        left_layout.addSpacing(8)

        # -- TTS Settings --
        left_layout.addWidget(self._section("TEXT-TO-SPEECH"))

        self._voice_combo = QComboBox()
        self._voice_combo.addItem("Loading voices...")
        left_layout.addWidget(self._voice_combo)

        speed_row = QHBoxLayout()
        speed_row.addWidget(QLabel("Speed"))
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(50, 200)
        self._speed_slider.setValue(100)
        self._speed_label = QLabel("1.0x")
        self._speed_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 12px;")
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_label.setText(f"{v / 100:.1f}x")
        )
        speed_row.addWidget(self._speed_slider)
        speed_row.addWidget(self._speed_label)
        left_layout.addLayout(speed_row)

        self._test_tts_btn = QPushButton("Test TTS")
        self._test_tts_btn.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.TEXT_PRIMARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 8px; font-size: 12px;"
        )
        self._test_tts_btn.clicked.connect(self._test_tts)
        left_layout.addWidget(self._test_tts_btn)

        left_layout.addSpacing(8)

        # -- Output device --
        left_layout.addWidget(self._section("OUTPUT"))

        self._output_device_combo = QComboBox()
        self._output_device_combo.addItem("Loading devices...")
        left_layout.addWidget(self._output_device_combo)

        left_layout.addStretch()

        # -- Stats --
        left_layout.addWidget(self._section("STATS"))
        self._stat_stt = StatRow("STT engine")
        self._stat_tts = StatRow("TTS engine")
        self._stat_vad = StatRow("VAD")
        for w in [self._stat_stt, self._stat_tts, self._stat_vad]:
            left_layout.addWidget(w)

        root.addWidget(left)

        # Right: live transcript
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(8)

        header = QLabel("LIVE TRANSCRIPT")
        header.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px;"
        )
        right_layout.addWidget(header)

        self._transcript_scroll = QScrollArea()
        self._transcript_scroll.setObjectName("chatScroll")
        self._transcript_scroll.setWidgetResizable(True)
        self._transcript_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._transcript_container = QWidget()
        self._transcript_layout = QVBoxLayout(self._transcript_container)
        self._transcript_layout.setContentsMargins(8, 8, 8, 8)
        self._transcript_layout.setSpacing(8)
        self._transcript_layout.addStretch()

        self._no_transcript = QLabel("Voice transcript will appear here when listening.")
        self._no_transcript.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 14px; padding: 40px 0;"
        )
        self._no_transcript.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._transcript_layout.insertWidget(0, self._no_transcript)

        self._transcript_scroll.setWidget(self._transcript_container)
        right_layout.addWidget(self._transcript_scroll, 1)

        # Clear button
        clear_btn = QPushButton("Clear Transcript")
        clear_btn.setStyleSheet(
            f"background-color: {theme.BG_TERTIARY}; color: {theme.TEXT_SECONDARY}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 6px; padding: 8px; font-size: 12px;"
        )
        clear_btn.clicked.connect(self._clear_transcript)
        right_layout.addWidget(clear_btn)

        root.addWidget(right, 1)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: 11px; font-weight: 700; "
            f"letter-spacing: 1px; padding: 0 0 4px 0;"
        )
        return lbl

    # -- Data fetching --

    def _fetch_status(self) -> None:
        url = QUrl(f"{self._base_url}/voice-engine/status")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_status(reply))

    def _handle_status(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._engine_status.setText("Offline")
            self._engine_status.setStyleSheet(
                f"color: {theme.ERROR_TEXT}; font-size: 14px; font-weight: 600;"
            )
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            enabled = data.get("enabled", False)
            state = data.get("state", "unknown")
            if enabled:
                self._engine_status.setText("Active")
                self._engine_status.setStyleSheet(
                    f"color: {theme.SUCCESS}; font-size: 14px; font-weight: 600;"
                )
                self._engine_state.setText(f"State: {state}")
            else:
                self._engine_status.setText("Not Initialized")
                self._engine_status.setStyleSheet(
                    f"color: {theme.WARNING}; font-size: 14px; font-weight: 600;"
                )
                self._engine_state.setText("Start Emily with --voice to enable")
        except Exception:
            pass
        reply.deleteLater()

    def _fetch_audio_devices(self) -> None:
        url = QUrl(f"{self._base_url}/audio/devices")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_devices(reply))

    def _handle_devices(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            inputs = data.get("input_devices", [])
            outputs = data.get("output_devices", [])

            self._input_device_combo.clear()
            for dev in inputs:
                name = dev if isinstance(dev, str) else dev.get("name", str(dev))
                self._input_device_combo.addItem(name)
            if not inputs:
                self._input_device_combo.addItem("No input devices found")

            self._output_device_combo.clear()
            for dev in outputs:
                name = dev if isinstance(dev, str) else dev.get("name", str(dev))
                self._output_device_combo.addItem(name)
            if not outputs:
                self._output_device_combo.addItem("No output devices found")
        except Exception:
            pass
        reply.deleteLater()

    def _fetch_voices(self) -> None:
        url = QUrl(f"{self._base_url}/audio/voice/voices")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_voices(reply))

    def _handle_voices(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self._voice_combo.clear()
            self._voice_combo.addItem("Default")
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            voices_raw = data.get("voices", {})
            current = data.get("current_voice", "")
            self._voice_combo.clear()

            # API returns {"voices": {"kokoro": [...], "csm": [...]}} — flatten
            flat_voices: list[str] = []
            if isinstance(voices_raw, dict):
                for _engine_name, voice_list in voices_raw.items():
                    for v in voice_list:
                        name = v.get("name", v.get("id", str(v))) if isinstance(v, dict) else str(v)
                        flat_voices.append(name)
            elif isinstance(voices_raw, list):
                for v in voices_raw:
                    name = v if isinstance(v, str) else v.get("name", str(v))
                    flat_voices.append(name)

            for name in flat_voices:
                self._voice_combo.addItem(name)

            if not flat_voices:
                self._voice_combo.addItem("Default")
            elif current:
                idx = self._voice_combo.findText(current)
                if idx >= 0:
                    self._voice_combo.setCurrentIndex(idx)
        except Exception:
            self._voice_combo.clear()
            self._voice_combo.addItem("Default")
        reply.deleteLater()

    def _fetch_transcript(self) -> None:
        """Fetch recent voice transcript entries from the SSE log."""
        url = QUrl(f"{self._base_url}/logs/recent?n=20")
        reply = self._nam.get(QNetworkRequest(url))
        reply.finished.connect(lambda: self._handle_transcript(reply))

    def _handle_transcript(self, reply: QNetworkReply) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            reply.deleteLater()
            return
        try:
            data = json.loads(bytes(reply.readAll().data()).decode())
            logs = data.get("logs", [])
            voice_entries = [
                e
                for e in logs
                if any(k in e.get("event", "") for k in ("stt_", "tts_", "voice_", "wake_"))
            ]
            if voice_entries:
                self._no_transcript.setVisible(False)
                for entry in voice_entries[-5:]:
                    event = entry.get("event", "")
                    text = entry.get("text", entry.get("transcript", ""))
                    if text:
                        self._add_transcript_entry(event, text)
        except Exception:
            pass
        reply.deleteLater()

    # -- Actions --

    def _on_mic_toggle(self, checked: bool) -> None:
        if checked:
            self._mic_btn.setText("Stop Listening")
            self._mic_btn.setStyleSheet(
                f"background-color: {theme.ERROR_TEXT}; color: white; "
                f"border: none; border-radius: 8px; font-size: 14px; font-weight: 700;"
            )
            self._transcript_timer.start(2000)
            self._no_transcript.setVisible(False)
        else:
            self._mic_btn.setText("Start Listening")
            self._mic_btn.setStyleSheet("")  # Reset to default
            self._transcript_timer.stop()

    def _test_tts(self) -> None:
        url = QUrl(f"{self._base_url}/audio/voice/test-tts")
        req = QNetworkRequest(url)
        req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
        payload = json.dumps({"text": "Hello, I'm Emily. Testing voice output."}).encode()
        self._nam.post(req, QByteArray(payload))

    def _add_transcript_entry(self, event: str, text: str) -> None:
        role = "Emily" if "tts" in event or "emily" in event.lower() else "You"
        color = theme.ACCENT if role == "You" else "#c9a0dc"

        entry = QLabel(f"<b style='color:{color}'>{role}:</b> {text}")
        entry.setWordWrap(True)
        entry.setStyleSheet(f"color: {theme.TEXT_PRIMARY}; font-size: 13px; padding: 4px 8px;")
        entry.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        count = self._transcript_layout.count()
        self._transcript_layout.insertWidget(count - 1, entry)

        QTimer.singleShot(
            10,
            lambda: self._transcript_scroll.verticalScrollBar().setValue(
                self._transcript_scroll.verticalScrollBar().maximum()
            ),
        )

    def _clear_transcript(self) -> None:
        while self._transcript_layout.count() > 1:
            item = self._transcript_layout.takeAt(0)
            if item and item.widget() and item.widget() is not self._no_transcript:
                item.widget().deleteLater()
        self._no_transcript.setVisible(True)
