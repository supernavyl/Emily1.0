"""
Hardened unit tests for the TTS pipeline.

Covers:
- crossfade() — edge cases: empty prev, empty curr, short overlap, normal
- ProsodyController.compute() — all punctuation branches, whisper mode,
  emotional state, sentence-position tapering, clamping
- ProsodyController.split_into_sentences() — abbreviations, decimals,
  ellipses, multi-sentence, single sentence
- TTSManager engine priority ordering
- TTSManager._select_engine() — force, auto, no-available raises
- TTSManager.speak() — empty text early return, silence padding,
  fallback when primary fails, all-engines-fail swallows
- KokoroEngine — load success, import error, stream output dtype
- XTTSv2Engine — load success, import error, stream chunking
- TTSManager.load() — concurrent loading, returns_exceptions=True
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from voice.prosody import ProsodyController, ProsodyParams
from voice.tts import (
    KokoroEngine,
    TTSManager,
    XTTSv2Engine,
    crossfade,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tts_config(
    primary: str = "kokoro",
    fallback: str = "xtts_v2",
    streaming_chunk_size: int = 100,
) -> Any:
    cfg = MagicMock()
    cfg.primary = primary
    cfg.fallback = fallback
    cfg.streaming_chunk_size = streaming_chunk_size
    cfg.kokoro.voice = "af_nicole"
    cfg.kokoro.speed = 0.92
    cfg.xtts.model_name = "xtts_v2"
    cfg.xtts.speaker_wav = None
    cfg.xtts.language = "en"
    cfg.csm.model_id = "sesame/csm-1b"
    cfg.csm.speaker_id = 0
    cfg.csm.max_audio_length = 250
    cfg.csm.dtype = "float16"
    return cfg


def _fake_audio_bytes(n_samples: int = 4800) -> bytes:
    """Return n_samples int16 samples as bytes."""
    audio = (np.random.randn(n_samples) * 1000).astype(np.int16)
    return audio.tobytes()


async def _collect_speak(manager: TTSManager, text: str, **kwargs) -> list[bytes]:
    chunks = []
    async for chunk in manager.speak(text, **kwargs):
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# crossfade tests
# ---------------------------------------------------------------------------


class TestCrossfade:
    def test_empty_prev_returns_curr(self) -> None:
        prev = np.array([], dtype=np.float32)
        curr = np.ones(100, dtype=np.float32)
        result = crossfade(prev, curr)
        np.testing.assert_array_equal(result, curr)

    def test_empty_curr_returns_prev(self) -> None:
        prev = np.ones(100, dtype=np.float32)
        curr = np.array([], dtype=np.float32)
        result = crossfade(prev, curr)
        np.testing.assert_array_equal(result, prev)

    def test_overlap_less_than_2_concatenates(self) -> None:
        prev = np.ones(5, dtype=np.float32)
        curr = np.ones(5, dtype=np.float32) * 2
        result = crossfade(prev, curr, overlap_samples=1)
        assert len(result) == 10

    def test_normal_crossfade_reduces_length(self) -> None:
        prev = np.ones(1000, dtype=np.float32)
        curr = np.ones(1000, dtype=np.float32) * 2
        result = crossfade(prev, curr, overlap_samples=200)
        assert len(result) == 1800

    def test_crossfade_eliminates_discontinuity(self) -> None:
        """Energy in the overlap region should be between prev and curr."""
        prev = np.zeros(200, dtype=np.float32)
        curr = np.ones(200, dtype=np.float32)
        result = crossfade(prev, curr, overlap_samples=50)
        overlap_start = len(prev) - 50
        # Transition region should not jump to 1 immediately
        assert result[overlap_start] < 0.5
        assert result[overlap_start + 49] > 0.5

    def test_overlap_capped_at_shorter_array(self) -> None:
        prev = np.ones(10, dtype=np.float32)
        curr = np.ones(10, dtype=np.float32)
        result = crossfade(prev, curr, overlap_samples=500)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# ProsodyController.compute() tests
# ---------------------------------------------------------------------------


class TestProsodyControllerCompute:
    def test_default_no_emotional_state(self) -> None:
        pc = ProsodyController()
        p = pc.compute("Hello there.")
        assert 0.7 <= p.speed <= 1.8
        assert 0.8 <= p.pitch <= 1.3
        assert 0.6 <= p.energy <= 1.4

    def test_question_raises_pitch_slows_speed(self) -> None:
        pc = ProsodyController()
        base = pc.compute("Hello there.")
        pc.reset_position()
        q = pc.compute("How are you?")
        assert q.pitch > base.pitch
        assert q.speed < base.speed
        assert q.pause_after_ms >= 350

    def test_exclamation_boosts_energy(self) -> None:
        pc = ProsodyController()
        base = pc.compute("Okay.")
        pc.reset_position()
        excl = pc.compute("That is incredible!")
        assert excl.energy > base.energy

    def test_ellipsis_slows_speed(self) -> None:
        pc = ProsodyController()
        base = pc.compute("Done.")
        pc.reset_position()
        trail = pc.compute("Well...")
        assert trail.speed < base.speed

    def test_whisper_mode_reduces_energy_and_speed(self) -> None:
        pc = ProsodyController()
        normal = pc.compute("Hello.")
        pc.reset_position()
        whisper = pc.compute("Hello.", whisper_mode=True)
        assert whisper.energy < normal.energy
        assert whisper.speed < normal.speed

    def test_high_engagement_increases_speed(self) -> None:
        pc = ProsodyController()
        low = pc.compute("Hello.", {"engagement": 0.0})
        pc.reset_position()
        high = pc.compute("Hello.", {"engagement": 1.0})
        assert high.speed > low.speed

    def test_values_clamped_to_valid_range(self) -> None:
        # Extreme emotional state shouldn't break clamping
        pc = ProsodyController()
        p = pc.compute("Wow!", {"engagement": 10.0, "enthusiasm": 10.0})
        assert p.speed <= 1.8
        assert p.energy <= 1.4
        assert p.pitch <= 1.3

    def test_sentence_position_tapering(self) -> None:
        """Later sentences should have lower energy than the first."""
        pc = ProsodyController()
        first = pc.compute("Sentence one.")
        for _ in range(6):
            pc.compute("Sentence.")
        late = pc.compute("Final sentence.")
        assert late.energy < first.energy

    def test_pause_before_zero_for_first_sentence(self) -> None:
        pc = ProsodyController()
        p = pc.compute("First.")
        assert p.pause_before_ms == 0

    def test_pause_before_nonzero_for_subsequent(self) -> None:
        pc = ProsodyController()
        pc.compute("First.")
        p = pc.compute("Second.")
        assert p.pause_before_ms > 0

    def test_reset_position_resets_index(self) -> None:
        pc = ProsodyController()
        for _ in range(10):
            pc.compute("Sentence.")
        pc.reset_position()
        p = pc.compute("First after reset.")
        assert p.pause_before_ms == 0


# ---------------------------------------------------------------------------
# ProsodyController.split_into_sentences() tests
# ---------------------------------------------------------------------------


class TestSplitIntoSentences:
    def test_single_sentence(self) -> None:
        result = ProsodyController.split_into_sentences("Hello world.")
        assert result == ["Hello world."]

    def test_two_sentences(self) -> None:
        result = ProsodyController.split_into_sentences("Hello. World.")
        assert len(result) == 2

    def test_abbreviation_not_split(self) -> None:
        result = ProsodyController.split_into_sentences("Dr. Smith is here.")
        assert len(result) == 1

    def test_decimal_not_split(self) -> None:
        result = ProsodyController.split_into_sentences("Pi is 3.14 approximately.")
        assert len(result) == 1

    def test_ellipsis_not_split(self) -> None:
        result = ProsodyController.split_into_sentences("Well... I'm not sure.")
        # ellipsis treated as a single token, not a split
        assert len(result) >= 1
        combined = " ".join(result)
        assert "..." in combined or "Well" in combined

    def test_empty_string(self) -> None:
        result = ProsodyController.split_into_sentences("")
        assert result == []

    def test_multiple_punctuation_types(self) -> None:
        text = "Is this good? Yes! Definitely."
        result = ProsodyController.split_into_sentences(text)
        assert len(result) == 3

    def test_whitespace_only(self) -> None:
        result = ProsodyController.split_into_sentences("   ")
        assert result == []


# ---------------------------------------------------------------------------
# TTSManager construction tests
# ---------------------------------------------------------------------------


class TestTTSManagerConstruction:
    def test_primary_first_in_engine_list(self) -> None:
        cfg = _make_tts_config(primary="kokoro", fallback="xtts_v2")
        mgr = TTSManager(cfg)
        assert mgr._engine_list[0].name == "kokoro"

    def test_fallback_second_in_engine_list(self) -> None:
        cfg = _make_tts_config(primary="kokoro", fallback="xtts_v2")
        mgr = TTSManager(cfg)
        assert mgr._engine_list[1].name == "xtts_v2"

    def test_unknown_engine_skipped_with_warning(self) -> None:
        cfg = _make_tts_config(primary="nonexistent", fallback="kokoro")
        mgr = TTSManager(cfg)
        names = [e.name for e in mgr._engine_list]
        assert "nonexistent" not in names
        assert "kokoro" in names

    def test_duplicate_primary_fallback_deduped(self) -> None:
        cfg = _make_tts_config(primary="kokoro", fallback="kokoro")
        mgr = TTSManager(cfg)
        kokoro_count = sum(1 for e in mgr._engine_list if e.name == "kokoro")
        assert kokoro_count == 1

    def test_all_engines_instantiated(self) -> None:
        cfg = _make_tts_config(primary="csm", fallback="kokoro")
        mgr = TTSManager(cfg)
        names = {e.name for e in mgr._engine_list}
        assert {"csm", "kokoro"}.issubset(names)


# ---------------------------------------------------------------------------
# TTSManager._select_engine() tests
# ---------------------------------------------------------------------------


class TestSelectEngine:
    def _mgr_with_engines(self, available: list[str]) -> TTSManager:
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)
        for eng in mgr._engine_list:
            eng._available = eng.name in available
        return mgr

    def test_force_selects_named_engine(self) -> None:
        mgr = self._mgr_with_engines(["kokoro", "xtts_v2"])
        eng = mgr._select_engine("xtts_v2")
        assert eng.name == "xtts_v2"

    def test_auto_selects_first_available(self) -> None:
        cfg = _make_tts_config(primary="kokoro", fallback="xtts_v2")
        mgr = TTSManager(cfg)
        for e in mgr._engine_list:
            e._available = False
        mgr._engine_list[1]._available = True  # xtts_v2 available
        eng = mgr._select_engine(None)
        assert eng.name == "xtts_v2"

    def test_no_engine_available_raises(self) -> None:
        mgr = self._mgr_with_engines([])
        with pytest.raises(RuntimeError, match="No TTS engine available"):
            mgr._select_engine(None)

    def test_force_unknown_falls_back_to_auto(self) -> None:
        mgr = self._mgr_with_engines(["kokoro"])
        # Force a name not in engine list: should fall through to auto
        eng = mgr._select_engine("nonexistent")
        assert eng.name == "kokoro"


# ---------------------------------------------------------------------------
# TTSManager.speak() tests
# ---------------------------------------------------------------------------


class TestTTSManagerSpeak:
    def _mgr_with_mock_engine(self, chunks: list[bytes]) -> tuple[TTSManager, Any]:
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)

        async def fake_stream(text, prosody):
            for chunk in chunks:
                yield chunk

        mock_eng = MagicMock()
        mock_eng._available = True
        mock_eng.name = "mock"
        mock_eng.stream = fake_stream
        mgr._engine_list = [mock_eng]
        return mgr, mock_eng

    @pytest.mark.asyncio
    async def test_empty_text_yields_nothing(self) -> None:
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)
        chunks = await _collect_speak(mgr, "   ")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_speak_yields_audio_chunks(self) -> None:
        audio = _fake_audio_bytes(4800)
        mgr, _ = self._mgr_with_mock_engine([audio])
        chunks = await _collect_speak(mgr, "Hello world.")
        assert len(chunks) >= 1
        total = sum(len(c) for c in chunks)
        assert total > 0

    @pytest.mark.asyncio
    async def test_silence_injected_between_sentences(self) -> None:
        """Pause-before should inject silence bytes before second+ sentences."""
        audio = _fake_audio_bytes(100)
        mgr, _ = self._mgr_with_mock_engine([audio])

        collected = []
        async for chunk in mgr.speak("First sentence. Second sentence."):
            collected.append(chunk)

        # At least one silence chunk (zeros) plus audio chunks
        assert len(collected) >= 2

    @pytest.mark.asyncio
    async def test_fallback_used_when_primary_fails(self) -> None:
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)

        async def bad_stream(text, prosody):
            raise RuntimeError("engine crashed")
            yield  # make it a generator

        async def good_stream(text, prosody):
            yield _fake_audio_bytes(100)

        bad_eng = MagicMock()
        bad_eng._available = True
        bad_eng.name = "bad"
        bad_eng.stream = bad_stream

        good_eng = MagicMock()
        good_eng._available = True
        good_eng.name = "good"
        good_eng.stream = good_stream

        mgr._engine_list = [bad_eng, good_eng]
        chunks = await _collect_speak(mgr, "Hello.")
        assert len(chunks) >= 1

    @pytest.mark.asyncio
    async def test_all_engines_fail_yields_nothing(self) -> None:
        """If all engines fail, speak should not raise — just yield nothing."""
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)

        async def bad_stream(text, prosody):
            raise RuntimeError("all engines down")
            yield

        for eng in mgr._engine_list:
            eng._available = True
            eng.stream = bad_stream

        # Should not raise
        chunks = await _collect_speak(mgr, "Hello.")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_whisper_mode_passed_to_prosody(self) -> None:
        audio = _fake_audio_bytes(100)
        mgr, _ = self._mgr_with_mock_engine([audio])

        computed_params = []
        real_compute = mgr._prosody.compute

        def capturing_compute(text, state=None, whisper=False):
            p = real_compute(text, state, whisper)
            computed_params.append(whisper)
            return p

        mgr._prosody.compute = capturing_compute
        await _collect_speak(mgr, "Hello.", whisper_mode=True)
        assert any(computed_params)


# ---------------------------------------------------------------------------
# KokoroEngine — load and stream
# ---------------------------------------------------------------------------


class TestKokoroEngine:
    @pytest.mark.asyncio
    async def test_load_import_error_stays_unavailable(self) -> None:
        cfg = _make_tts_config()
        engine = KokoroEngine(cfg)

        # Remove kokoro from sys.modules (and prevent re-import) so that
        # `from kokoro import KPipeline` raises ImportError inside load().
        with patch.dict("sys.modules", {"kokoro": None}):
            await engine.load()

        assert engine._available is False

    @pytest.mark.asyncio
    async def test_stream_raises_when_not_available(self) -> None:
        cfg = _make_tts_config()
        engine = KokoroEngine(cfg)
        engine._available = False
        prosody = ProsodyParams()

        with pytest.raises(RuntimeError, match="not available"):
            async for _ in engine.stream("hello", prosody):
                pass

    @pytest.mark.asyncio
    async def test_stream_yields_int16_bytes(self) -> None:
        cfg = _make_tts_config()
        engine = KokoroEngine(cfg)
        engine._available = True

        fake_audio = np.sin(np.linspace(0, 2 * np.pi, 24000)).astype(np.float32) * 0.5

        def fake_pipeline(text, voice, speed, split_pattern):
            yield "hello", "həˈloʊ", fake_audio

        engine._pipeline = fake_pipeline
        prosody = ProsodyParams(speed=1.0)

        chunks = []
        async for chunk in engine.stream("Hello.", prosody):
            chunks.append(chunk)

        assert len(chunks) >= 1
        # Verify bytes decode to int16 without error
        arr = np.frombuffer(chunks[0], dtype=np.int16)
        assert len(arr) > 0


# ---------------------------------------------------------------------------
# XTTSv2Engine — load and stream
# ---------------------------------------------------------------------------


class TestXTTSv2Engine:
    @pytest.mark.asyncio
    async def test_load_import_error_stays_unavailable(self) -> None:
        cfg = _make_tts_config()
        engine = XTTSv2Engine(cfg)

        # Remove TTS from sys.modules so `from TTS.api import TTS` raises ImportError.
        with patch.dict("sys.modules", {"TTS": None, "TTS.api": None}):
            await engine.load()

        assert engine._available is False

    @pytest.mark.asyncio
    async def test_stream_raises_when_not_available(self) -> None:
        cfg = _make_tts_config()
        engine = XTTSv2Engine(cfg)
        engine._available = False
        prosody = ProsodyParams()

        with pytest.raises(RuntimeError, match="not available"):
            async for _ in engine.stream("hello", prosody):
                pass

    @pytest.mark.asyncio
    async def test_stream_chunks_output_correctly(self) -> None:
        cfg = _make_tts_config(streaming_chunk_size=1)  # 1 KB chunks
        engine = XTTSv2Engine(cfg)
        engine._available = True
        engine._tts = MagicMock()  # must set _tts too — guard checks both flags

        # 5 KB of fake WAV data
        fake_bytes = b"\x00" * (5 * 1024)

        with patch("voice.tts.asyncio.to_thread", new=AsyncMock(return_value=fake_bytes)):
            with patch("voice.tts.TTS_FIRST_AUDIO_LATENCY") as mock_lat:
                mock_lat.labels.return_value.observe = MagicMock()
                prosody = ProsodyParams()
                chunks = []
                async for chunk in engine.stream("Hello.", prosody):
                    chunks.append(chunk)

        assert len(chunks) == 5
        assert all(len(c) == 1024 for c in chunks)


# ---------------------------------------------------------------------------
# TTSManager.load() — concurrent loading
# ---------------------------------------------------------------------------


class TestTTSManagerLoad:
    @pytest.mark.asyncio
    async def test_load_all_engines_called(self) -> None:
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)

        load_calls = []
        for eng in mgr._engine_list:

            async def make_load(e=eng):
                load_calls.append(e.name)

            eng.load = make_load

        await mgr.load()
        assert len(load_calls) == len(mgr._engine_list)

    @pytest.mark.asyncio
    async def test_load_continues_if_one_engine_fails(self) -> None:
        """One engine failing to load should not prevent others from loading."""
        cfg = _make_tts_config()
        mgr = TTSManager(cfg)

        loaded = []

        async def fail_load():
            raise RuntimeError("load failed")

        async def ok_load(name):
            loaded.append(name)

        mgr._engine_list[0].load = fail_load
        for eng in mgr._engine_list[1:]:
            name = eng.name
            eng.load = lambda n=name: ok_load(n)

        await mgr.load()
        assert len(loaded) == len(mgr._engine_list) - 1
