"""
Emily Voice Dashboard — main window.

A standalone PySide6 QMainWindow that displays the full voice engine state,
mirroring every panel from the web voice dashboard.  Runs in-process with
main.py and reads data directly from the VoiceEngine via VoiceEnginePoller.

Layout:
    +-------------------------------------------------------+-------+
    | HERO (state orb, label, duration, TTS test)            |       |
    +-------------------------------------------------------+ STATS |
    | TTS | STT | WAKE WORD | SPEAKERS                      |       |
    +-------------------------------------------------------+ SPKRS |
    | AUDIO LEVELS (waveform + SNR)                          | DEVS  |
    +-----------------------------+-------------------------+ SYS   |
    | LIVE TRANSCRIPT             | PIPELINE MODULES        |       |
    +-----------------------------+-------------------------+       |
    | EMOTION  | TURN DETECTION   | RHYTHM SYNC             |       |
    +---------+------------------+---------------------------+-------+
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ui.voice.poller import VoiceEnginePoller
from ui.voice.widgets import (
    ACCENT,
    BG_PRIMARY,
    BORDER,
    CYAN,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    AudioLevelsWidget,
    DeviceSelectorWidget,
    EmotionWidget,
    HeroWidget,
    PipelineWidget,
    RhythmWidget,
    SessionStatsWidget,
    SpeakersWidget,
    StatusCardsWidget,
    SystemWidget,
    TranscriptWidget,
    TurnDetectionWidget,
    VoiceDebugWidget,
)


class _VoiceBrainSignals(QObject):
    """Qt signal bridge for BrainEventHub events in the Voice Dashboard."""

    perception_event = Signal(dict)
    llm_event = Signal(dict)
    fsm_event = Signal(dict)
    mic_test_done = Signal(bool, float)

_DARK_STYLESHEET = f"""
QMainWindow, QWidget {{
    background: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    font-family: Inter, "Segoe UI", system-ui, sans-serif;
    font-size: 12px;
}}
QSplitter::handle {{
    background: {BORDER};
    width: 2px;
    height: 2px;
}}
QScrollArea {{
    border: none;
    background: {BG_PRIMARY};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


class VoiceDashboard(QMainWindow):
    """
    Standalone desktop window for Emily's voice engine.

    Takes a VoiceEnginePoller and connects its ``data_updated`` signal
    to every widget's ``update()`` method.
    """

    def __init__(
        self,
        poller: VoiceEnginePoller,
        brain_hub: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._poller = poller
        self._brain_hub = brain_hub
        self.setWindowTitle("Emily — Voice Mode")
        self.resize(1400, 900)
        self.setStyleSheet(_DARK_STYLESHEET)

        self._signals = _VoiceBrainSignals(self)
        if brain_hub is not None:
            brain_hub.attach_signals(self._signals)

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        main_scroll = QScrollArea()
        main_scroll.setWidgetResizable(True)
        main_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        main_widget = QWidget()
        main_col = QVBoxLayout(main_widget)
        main_col.setContentsMargins(20, 12, 12, 20)
        main_col.setSpacing(12)

        header = self._build_header()
        main_col.addLayout(header)

        self._hero = HeroWidget()
        main_col.addWidget(self._hero)

        self._status_cards = StatusCardsWidget()
        main_col.addWidget(self._status_cards)

        self._audio_levels = AudioLevelsWidget()
        main_col.addWidget(self._audio_levels)

        mid_split = QSplitter(Qt.Orientation.Horizontal)
        self._transcript = TranscriptWidget()
        self._pipeline = PipelineWidget()
        mid_split.addWidget(self._transcript)
        mid_split.addWidget(self._pipeline)
        mid_split.setSizes([500, 500])
        main_col.addWidget(mid_split, 1)

        self._voice_debug = VoiceDebugWidget()
        main_col.addWidget(self._voice_debug, 1)
        self._signals.perception_event.connect(self._voice_debug.on_perception)
        self._signals.llm_event.connect(self._voice_debug.on_llm)
        self._signals.fsm_event.connect(self._voice_debug.on_fsm)

        bottom_split = QSplitter(Qt.Orientation.Horizontal)
        self._emotion = EmotionWidget()
        self._turn = TurnDetectionWidget()
        self._rhythm = RhythmWidget()
        bottom_split.addWidget(self._emotion)
        bottom_split.addWidget(self._turn)
        bottom_split.addWidget(self._rhythm)
        bottom_split.setSizes([300, 300, 400])
        main_col.addWidget(bottom_split)

        main_scroll.setWidget(main_widget)
        splitter.addWidget(main_scroll)

        sidebar_scroll = QScrollArea()
        sidebar_scroll.setWidgetResizable(True)
        sidebar_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        sidebar_widget = QWidget()
        sidebar_widget.setFixedWidth(300)
        sidebar = QVBoxLayout(sidebar_widget)
        sidebar.setContentsMargins(8, 12, 16, 20)
        sidebar.setSpacing(12)

        self._session_stats = SessionStatsWidget()
        sidebar.addWidget(self._session_stats)

        self._speakers = SpeakersWidget()
        sidebar.addWidget(self._speakers)

        self._device_selector = DeviceSelectorWidget()
        sidebar.addWidget(self._device_selector)

        self._system = SystemWidget()
        sidebar.addWidget(self._system)

        sidebar.addStretch()
        sidebar_scroll.setWidget(sidebar_widget)
        splitter.addWidget(sidebar_scroll)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        root.addWidget(splitter)

        self._all_widgets = [
            self._hero,
            self._status_cards,
            self._audio_levels,
            self._pipeline,
            self._emotion,
            self._turn,
            self._rhythm,
            self._session_stats,
            self._speakers,
            self._device_selector,
            self._system,
            self._voice_debug,
        ]

        poller.data_updated.connect(self._on_data)
        poller.transcript_received.connect(self._on_transcript)
        self._device_selector.device_changed.connect(poller.change_device)

        self._hero._tts_btn.clicked.connect(self._test_tts)
        self._audio_levels.mic_test_requested.connect(self._test_mic)
        self._signals.mic_test_done.connect(self._audio_levels.show_mic_test_result)
        self._signals.perception_event.connect(self._on_emily_spoke)

    def _build_header(self) -> QHBoxLayout:
        """Build the top header row."""
        row = QHBoxLayout()
        title = QLabel("EMILY")
        title.setStyleSheet(
            f"color: {ACCENT}; font-size: 18px; font-weight: bold; "
            f"letter-spacing: 2px;"
        )
        subtitle = QLabel("Voice Mode")
        subtitle.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 14px; margin-left: 8px;"
        )
        row.addWidget(title)
        row.addWidget(subtitle)
        row.addStretch()

        self._status_badge = QLabel("OFFLINE")
        self._status_badge.setStyleSheet(
            f"background: {BORDER}; color: {TEXT_MUTED}; border-radius: 10px; "
            f"padding: 4px 14px; font-size: 11px; font-weight: bold;"
        )
        row.addWidget(self._status_badge)

        self._uptime_label = QLabel("Session: 0s")
        self._uptime_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 11px; margin-left: 12px;"
        )
        row.addWidget(self._uptime_label)
        return row

    @Slot(dict)
    def _on_data(self, data: dict[str, Any]) -> None:
        """Distribute poller data to all widgets."""
        running = data.get("running", False)
        if running:
            self._status_badge.setText("ONLINE")
            self._status_badge.setStyleSheet(
                f"background: #0d3320; color: {CYAN}; border-radius: 10px; "
                f"padding: 4px 14px; font-size: 11px; font-weight: bold;"
            )
        else:
            engine_avail = data.get("engine_available", False)
            if engine_avail:
                self._status_badge.setText("STARTING")
                self._status_badge.setStyleSheet(
                    f"background: #3d2d00; color: {TEXT_PRIMARY}; border-radius: 10px; "
                    f"padding: 4px 14px; font-size: 11px; font-weight: bold;"
                )
            else:
                self._status_badge.setText("OFFLINE")
                self._status_badge.setStyleSheet(
                    f"background: {BORDER}; color: {TEXT_MUTED}; border-radius: 10px; "
                    f"padding: 4px 14px; font-size: 11px; font-weight: bold;"
                )

        uptime = data.get("uptime_s", 0)
        m, s = divmod(int(uptime), 60)
        self._uptime_label.setText(f"Session: {m}m {s:02d}s" if m else f"Session: {s}s")

        for widget in self._all_widgets:
            widget.update(data)

    @Slot(str, str)
    def _on_transcript(self, role: str, text: str) -> None:
        """Add a transcript entry."""
        self._transcript.add_entry(role, text)

    @Slot(dict)
    def _on_emily_spoke(self, event: dict[str, Any]) -> None:
        """Feed Emily's spoken text into the transcript widget."""
        if event.get("kind") == "emily_spoke":
            text = event.get("data", {}).get("text", "")
            if text:
                self._transcript.add_entry("emily", text)

    def _test_mic(self) -> None:
        """Record 3 seconds of audio, play it back, and show pass/fail."""
        import asyncio

        engine = self._poller._engine
        if engine is None:
            return
        modules = getattr(engine, "_modules", None) or {}
        capture = modules.get("audio_capture")
        if capture is None:
            return

        self._audio_levels.show_mic_test_recording()

        async def _record_and_playback() -> None:
            import numpy as np

            chunks: list[Any] = []
            chunk_ms = getattr(
                getattr(capture, "_config", None), "input_chunk_ms", 30
            )
            n_chunks = int(3000 / max(chunk_ms, 1))
            try:
                for _ in range(n_chunks):
                    chunk = await capture.get_input_chunk()
                    if chunk is not None:
                        data = getattr(chunk, "data", None)
                        if data is not None:
                            chunks.append(np.asarray(data, dtype=np.float32))
                    await asyncio.sleep(chunk_ms / 1000.0)

                if chunks:
                    recording = np.concatenate(chunks)
                    peak_rms = float(np.sqrt(np.mean(recording ** 2)))
                    peak_db = float(20 * np.log10(max(peak_rms, 1e-10)))
                    passed = peak_db > -40.0

                    try:
                        await capture.write_output(recording)
                    except Exception:
                        pass

                    self._signals.mic_test_done.emit(passed, peak_db)
                else:
                    self._signals.mic_test_done.emit(False, -80.0)
            except Exception:
                self._signals.mic_test_done.emit(False, -80.0)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_record_and_playback())
        except RuntimeError:
            self._audio_levels.show_mic_test_result(False, -80.0)

    def _test_tts(self) -> None:
        """Speak a test phrase through the voice engine's TTS pipeline."""
        import asyncio

        engine = self._poller._engine
        if engine is None:
            return
        modules = getattr(engine, "_modules", None) or {}
        tts = modules.get("tts_engine")
        capture = modules.get("audio_capture")
        if tts is None:
            return

        async def _speak() -> None:
            try:
                audio = await tts.speak(
                    "Hello, I'm Emily. Can you hear me clearly?"
                )
                if capture is not None and audio is not None:
                    await capture.write_output(audio)
            except Exception:
                pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_speak())
        except RuntimeError:
            pass
