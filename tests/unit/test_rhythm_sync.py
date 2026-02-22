"""
Tests for the rhythm synchronization / entrainment engine.

Verifies:
- Entrainment blending at various degrees
- Breath interval included in targets
- EMA profile updates from prosody
- Response gap recording
- Profile export/import round-trip
"""

from __future__ import annotations

import pytest
import numpy as np

from conversation.rhythm_sync import (
    RhythmProfile,
    RhythmSynchronizer,
    RhythmTargets,
)
from perception.audio.prosody_analyzer import ProsodyFeatures


@pytest.fixture
def sync() -> RhythmSynchronizer:
    """Create a synchronizer with default 0.4 entrainment."""
    return RhythmSynchronizer(entrainment_degree=0.4)


class TestEntrainmentBlending:
    """Test that targets blend Emily baseline with user profile."""

    def test_zero_entrainment_returns_baseline(self) -> None:
        """At entrainment 0.0, targets should match Emily's baseline."""
        s = RhythmSynchronizer(entrainment_degree=0.0)
        t = s.get_targets()
        assert t.speaking_rate_syl_s == pytest.approx(4.2, abs=0.01)
        assert t.pause_duration_ms == pytest.approx(250.0, abs=0.1)
        assert t.phrase_length_words == 10
        assert t.breath_interval_s == pytest.approx(20.0, abs=0.1)

    def test_full_entrainment_returns_user(self) -> None:
        """At entrainment 1.0, targets should match the user profile."""
        s = RhythmSynchronizer(entrainment_degree=1.0)
        s._user_profile.speaking_rate_syl_s = 5.0
        s._user_profile.pause_duration_ms = 400.0
        s._user_profile.phrase_length_words = 6
        s._user_profile.breath_interval_s = 15.0
        t = s.get_targets()
        assert t.speaking_rate_syl_s == pytest.approx(5.0, abs=0.01)
        assert t.pause_duration_ms == pytest.approx(400.0, abs=0.1)
        assert t.phrase_length_words == 6
        assert t.breath_interval_s == pytest.approx(15.0, abs=0.1)

    def test_default_entrainment_blends(self, sync: RhythmSynchronizer) -> None:
        """At 0.4, targets should be 60% baseline + 40% user."""
        sync._user_profile.speaking_rate_syl_s = 6.0
        t = sync.get_targets()
        expected = 4.2 * 0.6 + 6.0 * 0.4
        assert t.speaking_rate_syl_s == pytest.approx(expected, abs=0.01)


class TestBreathIntervalTarget:
    """Test that breath_interval_s is included in targets."""

    def test_breath_interval_present(self, sync: RhythmSynchronizer) -> None:
        """RhythmTargets should have a breath_interval_s field."""
        t = sync.get_targets()
        assert hasattr(t, "breath_interval_s")
        assert 10.0 <= t.breath_interval_s <= 30.0

    def test_breath_interval_blended(self) -> None:
        """Breath interval should blend between baseline and user."""
        s = RhythmSynchronizer(entrainment_degree=0.5)
        s._user_profile.breath_interval_s = 12.0
        s._emily_baseline.breath_interval_s = 20.0
        t = s.get_targets()
        expected = 20.0 * 0.5 + 12.0 * 0.5
        assert t.breath_interval_s == pytest.approx(expected, abs=0.1)

    def test_breath_interval_clamped(self) -> None:
        """Extreme user breath intervals should be clamped to 10-30s."""
        s = RhythmSynchronizer(entrainment_degree=1.0)
        s._user_profile.breath_interval_s = 5.0
        t = s.get_targets()
        assert t.breath_interval_s >= 10.0

        s._user_profile.breath_interval_s = 50.0
        t = s.get_targets()
        assert t.breath_interval_s <= 30.0


class TestRateClipping:
    """Test that target values are clipped to safe ranges."""

    def test_rate_clipped_high(self) -> None:
        """Speaking rate above 7.0 syl/s should be clipped."""
        s = RhythmSynchronizer(entrainment_degree=1.0)
        s._user_profile.speaking_rate_syl_s = 10.0
        t = s.get_targets()
        assert t.speaking_rate_syl_s <= 7.0

    def test_rate_clipped_low(self) -> None:
        """Speaking rate below 2.0 syl/s should be clipped."""
        s = RhythmSynchronizer(entrainment_degree=1.0)
        s._user_profile.speaking_rate_syl_s = 0.5
        t = s.get_targets()
        assert t.speaking_rate_syl_s >= 2.0


class TestEMAUpdates:
    """Test that prosody updates adjust the user profile via EMA."""

    def test_rate_updates(self, sync: RhythmSynchronizer) -> None:
        """Speaking rate should move toward new observations."""
        initial = sync._user_profile.speaking_rate_syl_s
        for _ in range(20):
            sync.update_from_prosody(ProsodyFeatures(speaking_rate_syl_s=6.0))
        assert sync._user_profile.speaking_rate_syl_s > initial

    def test_pause_updates(self, sync: RhythmSynchronizer) -> None:
        """Pause duration should move toward new observations."""
        initial = sync._user_profile.pause_duration_ms
        for _ in range(20):
            sync.update_from_prosody(ProsodyFeatures(pause_duration_ms=500.0))
        assert sync._user_profile.pause_duration_ms > initial

    def test_response_gap_updates(self, sync: RhythmSynchronizer) -> None:
        """Response latency should move toward recorded gaps."""
        initial = sync._user_profile.response_latency_ms
        for _ in range(20):
            sync.record_response_gap(600.0)
        assert sync._user_profile.response_latency_ms > initial

    def test_sample_count_increments(self, sync: RhythmSynchronizer) -> None:
        """n_samples should increment with each prosody update."""
        sync.update_from_prosody(ProsodyFeatures(speaking_rate_syl_s=5.0))
        sync.update_from_prosody(ProsodyFeatures(speaking_rate_syl_s=5.0))
        assert sync._user_profile.n_samples == 2


class TestProfileExportImport:
    """Test round-trip serialization of rhythm profiles."""

    def test_export_import_roundtrip(self, sync: RhythmSynchronizer) -> None:
        """Exported profile should restore identically on import."""
        sync._user_profile.speaking_rate_syl_s = 5.5
        sync._user_profile.pause_duration_ms = 420.0
        sync._user_profile.phrase_length_words = 7
        sync._user_profile.response_latency_ms = 280.0
        sync._user_profile.breath_interval_s = 18.0
        sync._user_profile.n_samples = 42

        data = sync.export_profile()

        sync2 = RhythmSynchronizer()
        sync2.import_profile(data)

        assert sync2._user_profile.speaking_rate_syl_s == pytest.approx(5.5)
        assert sync2._user_profile.pause_duration_ms == pytest.approx(420.0)
        assert sync2._user_profile.phrase_length_words == 7
        assert sync2._user_profile.response_latency_ms == pytest.approx(280.0)
        assert sync2._user_profile.breath_interval_s == pytest.approx(18.0)
        assert sync2._user_profile.n_samples == 42

    def test_export_contains_breath(self, sync: RhythmSynchronizer) -> None:
        """Exported dict should contain breath_interval_s."""
        data = sync.export_profile()
        assert "breath_interval_s" in data


class TestConvenienceMethods:
    """Test single-value convenience accessors."""

    def test_get_target_speaking_rate(self, sync: RhythmSynchronizer) -> None:
        """Should match the full targets object."""
        assert sync.get_target_speaking_rate() == sync.get_targets().speaking_rate_syl_s

    def test_get_target_pause_duration(self, sync: RhythmSynchronizer) -> None:
        """Should match the full targets object."""
        assert sync.get_target_pause_duration() == sync.get_targets().pause_duration_ms

    def test_get_target_response_latency(self, sync: RhythmSynchronizer) -> None:
        """Should match the full targets object."""
        assert sync.get_target_response_latency_ms() == sync.get_targets().response_latency_ms

    def test_get_target_phrase_length(self, sync: RhythmSynchronizer) -> None:
        """Should match the full targets object."""
        assert sync.get_target_phrase_length() == sync.get_targets().phrase_length_words


class TestEntrainmentProperty:
    """Test the entrainment_degree property and setter."""

    def test_setter_clips(self) -> None:
        """Setting entrainment beyond 0-1 should be clipped."""
        s = RhythmSynchronizer()
        s.entrainment_degree = 1.5
        assert s.entrainment_degree <= 1.0

        s.entrainment_degree = -0.3
        assert s.entrainment_degree >= 0.0
