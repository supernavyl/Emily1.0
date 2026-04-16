"""Tests for Emily's self-evolving constitution system."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from persona.constitution import (
    _BIRTH_CONFIDENCE,
    ConstitutionManager,
)

# ── fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def mgr(tmp_path: Path) -> ConstitutionManager:
    """ConstitutionManager backed by a temp file."""
    path = tmp_path / "constitution.json"
    m = ConstitutionManager(path=str(path))
    m.load()
    return m


# ══════════════════════════════════════════════════════════════════
# PERSISTENCE
# ══════════════════════════════════════════════════════════════════


class TestConstitutionPersistence:
    def test_load_creates_empty_constitution_when_no_file(self, tmp_path: Path) -> None:
        path = tmp_path / "constitution.json"
        assert not path.exists()

        mgr = ConstitutionManager(path=str(path))
        mgr.load()

        assert path.exists()
        assert mgr.principles == []

    def test_load_reads_existing_principles(self, tmp_path: Path) -> None:
        path = tmp_path / "constitution.json"
        data = {
            "principles": [
                {
                    "id": "abc-123",
                    "text": "Honesty over comfort",
                    "source_episodes": ["ep-1"],
                    "born_at": "2026-01-15T00:00:00+00:00",
                    "evolved_at": None,
                    "confidence": 0.7,
                    "reinforcements": 3,
                    "challenges": 1,
                    "lineage": [],
                    "status": "active",
                }
            ]
        }
        path.write_text(json.dumps(data), encoding="utf-8")

        mgr = ConstitutionManager(path=str(path))
        mgr.load()

        assert len(mgr.principles) == 1
        p = mgr.principles[0]
        assert p.id == "abc-123"
        assert p.text == "Honesty over comfort"
        assert p.source_episodes == ["ep-1"]
        assert p.confidence == 0.7
        assert p.reinforcements == 3
        assert p.challenges == 1
        assert p.status == "active"

    def test_save_persists_to_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "constitution.json"

        mgr = ConstitutionManager(path=str(path))
        mgr.load()
        mgr.add_principle("Be direct", source_episodes=["ep-42"])
        mgr.save_sync()

        raw = json.loads(path.read_text(encoding="utf-8"))

        assert len(raw["principles"]) == 1
        assert raw["principles"][0]["text"] == "Be direct"
        assert raw["principles"][0]["source_episodes"] == ["ep-42"]
        assert raw["principles"][0]["confidence"] == _BIRTH_CONFIDENCE


# ══════════════════════════════════════════════════════════════════
# PRINCIPLE CRUD
# ══════════════════════════════════════════════════════════════════


class TestPrincipleCRUD:
    def test_add_principle_sets_birth_confidence(self, mgr: ConstitutionManager) -> None:
        p = mgr.add_principle("Clarity over cleverness")

        assert p.confidence == _BIRTH_CONFIDENCE
        assert p.status == "active"
        assert p.reinforcements == 0
        assert p.challenges == 0
        assert p.lineage == []
        assert p.evolved_at is None
        assert p.id  # non-empty uuid

    def test_reinforce_increases_confidence(self, mgr: ConstitutionManager) -> None:
        p = mgr.add_principle("Stay curious")
        original = p.confidence

        mgr.reinforce(p.id)

        assert p.confidence > original
        assert p.reinforcements == 1

    def test_challenge_decreases_confidence(self, mgr: ConstitutionManager) -> None:
        p = mgr.add_principle("Always respond immediately")
        original = p.confidence

        mgr.challenge(p.id)

        assert p.confidence < original
        assert p.challenges == 1

    def test_confidence_never_exceeds_bounds(self, mgr: ConstitutionManager) -> None:
        p = mgr.add_principle("Bounded principle")

        for _ in range(50):
            mgr.reinforce(p.id)
        assert p.confidence <= 1.0

        # Reset to test floor
        p2 = mgr.add_principle("Floor test")
        for _ in range(50):
            mgr.challenge(p2.id)
        assert p2.confidence >= 0.0

    def test_evolve_supersedes_old_and_preserves_lineage(self, mgr: ConstitutionManager) -> None:
        old = mgr.add_principle("Be brief")
        old_id = old.id

        # Reinforce a few times so state carries forward
        mgr.reinforce(old_id)
        mgr.reinforce(old_id)
        mgr.challenge(old_id)

        new = mgr.evolve_principle(old_id, "Be brief, but not at the cost of clarity")

        assert new is not None
        assert old.status == "superseded"
        assert old.evolved_at is not None
        assert new.status == "active"
        assert old_id in new.lineage
        assert new.challenges == 0
        assert new.reinforcements == old.reinforcements
        assert new.confidence == old.confidence

    def test_deprecate_marks_inactive(self, mgr: ConstitutionManager) -> None:
        p = mgr.add_principle("Deprecated test")

        mgr.deprecate(p.id)

        assert p.status == "deprecated"
        assert p not in mgr.active_principles


# ══════════════════════════════════════════════════════════════════
# PROMPT FORMATTING
# ══════════════════════════════════════════════════════════════════


class TestPromptFormatting:
    def test_empty_constitution_returns_empty_string(self, mgr: ConstitutionManager) -> None:
        assert mgr.get_for_prompt() == ""

    def test_formats_active_principles_by_confidence(self, mgr: ConstitutionManager) -> None:
        mgr.add_principle("Low confidence")
        high = mgr.add_principle("High confidence")

        # Boost high confidence above low
        for _ in range(10):
            mgr.reinforce(high.id)

        prompt = mgr.get_for_prompt()

        assert "MY CONSTITUTION" in prompt
        idx_high = prompt.index("High confidence")
        idx_low = prompt.index("Low confidence")
        assert idx_high < idx_low

    def test_excludes_deprecated_principles(self, mgr: ConstitutionManager) -> None:
        mgr.add_principle("I am active")
        dead = mgr.add_principle("I am deprecated")
        mgr.deprecate(dead.id)

        prompt = mgr.get_for_prompt()

        assert "I am active" in prompt
        assert "I am deprecated" not in prompt


# ══════════════════════════════════════════════════════════════════
# CONTRADICTION DETECTION
# ══════════════════════════════════════════════════════════════════


class TestContradictionDetection:
    def test_no_contradictions_when_healthy(self, mgr: ConstitutionManager) -> None:
        mgr.add_principle("Be honest")
        mgr.add_principle("Be kind")

        assert mgr.find_contradictions() == []

    def test_detects_highly_challenged_pair(self, mgr: ConstitutionManager) -> None:
        a = mgr.add_principle("Always be blunt")
        b = mgr.add_principle("Soften hard truths")

        for _ in range(4):
            mgr.challenge(a.id)
            mgr.challenge(b.id)

        contradictions = mgr.find_contradictions()

        assert len(contradictions) >= 1
        ids_in_contradictions = {(c[0].id, c[1].id) for c in contradictions}
        assert (a.id, b.id) in ids_in_contradictions or (b.id, a.id) in ids_in_contradictions
