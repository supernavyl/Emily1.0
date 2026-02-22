"""Tests for the skills system — custom skill persistence and merging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from emily_chat.emily.skills import (
    EMILY_SKILLS,
    EmilySkill,
    delete_custom_skill,
    get_all_skills,
    get_skill,
    load_custom_skills,
    save_custom_skill,
)


@pytest.fixture()
def custom_path(tmp_path: Path) -> Path:
    """Return a temporary path for custom_skills.json."""
    return tmp_path / "custom_skills.json"


class TestLoadCustomSkills:
    """Tests for load_custom_skills."""

    def test_empty_when_no_file(self, custom_path: Path) -> None:
        assert load_custom_skills(custom_path) == {}

    def test_loads_valid_json(self, custom_path: Path) -> None:
        data = {
            "my_skill": {
                "name": "My Skill",
                "icon": "\U0001f680",
                "description": "Test skill",
                "system_addition": "Be awesome.",
                "enable_thinking": True,
                "enable_web_search": False,
                "enable_code_execution": False,
                "temperature": 0.7,
            }
        }
        custom_path.parent.mkdir(parents=True, exist_ok=True)
        custom_path.write_text(json.dumps(data))
        skills = load_custom_skills(custom_path)
        assert "my_skill" in skills
        assert skills["my_skill"].name == "My Skill"
        assert skills["my_skill"].enable_thinking is True

    def test_invalid_json_returns_empty(self, custom_path: Path) -> None:
        custom_path.parent.mkdir(parents=True, exist_ok=True)
        custom_path.write_text("not json")
        assert load_custom_skills(custom_path) == {}


class TestSaveCustomSkill:
    """Tests for save_custom_skill."""

    def test_saves_new_skill(self, custom_path: Path) -> None:
        skill = EmilySkill(name="Test", icon="\u2b50", description="A test")
        save_custom_skill("test", skill, custom_path)
        loaded = load_custom_skills(custom_path)
        assert "test" in loaded
        assert loaded["test"].name == "Test"

    def test_overwrites_existing(self, custom_path: Path) -> None:
        skill_v1 = EmilySkill(name="V1", icon="\u2b50", description="First")
        skill_v2 = EmilySkill(name="V2", icon="\U0001f525", description="Second")
        save_custom_skill("s", skill_v1, custom_path)
        save_custom_skill("s", skill_v2, custom_path)
        loaded = load_custom_skills(custom_path)
        assert loaded["s"].name == "V2"

    def test_preserves_other_skills(self, custom_path: Path) -> None:
        save_custom_skill("a", EmilySkill(name="A", icon="a", description="a"), custom_path)
        save_custom_skill("b", EmilySkill(name="B", icon="b", description="b"), custom_path)
        loaded = load_custom_skills(custom_path)
        assert "a" in loaded
        assert "b" in loaded

    def test_roundtrip_temperature(self, custom_path: Path) -> None:
        skill = EmilySkill(name="T", icon="t", description="t", temperature=0.42)
        save_custom_skill("t", skill, custom_path)
        assert load_custom_skills(custom_path)["t"].temperature == 0.42


class TestDeleteCustomSkill:
    """Tests for delete_custom_skill."""

    def test_delete_existing(self, custom_path: Path) -> None:
        save_custom_skill("x", EmilySkill(name="X", icon="x", description="x"), custom_path)
        assert delete_custom_skill("x", custom_path) is True
        assert "x" not in load_custom_skills(custom_path)

    def test_delete_nonexistent(self, custom_path: Path) -> None:
        assert delete_custom_skill("nope", custom_path) is False


class TestGetAllSkills:
    """Tests for get_all_skills merging."""

    def test_includes_builtins(self, custom_path: Path) -> None:
        all_skills = get_all_skills(custom_path)
        for sid in EMILY_SKILLS:
            assert sid in all_skills

    def test_includes_custom(self, custom_path: Path) -> None:
        save_custom_skill("custom1", EmilySkill(name="C", icon="c", description="c"), custom_path)
        all_skills = get_all_skills(custom_path)
        assert "custom1" in all_skills

    def test_builtin_overrides_custom(self, custom_path: Path) -> None:
        save_custom_skill("code", EmilySkill(name="Fake", icon="f", description="f"), custom_path)
        all_skills = get_all_skills(custom_path)
        assert all_skills["code"].name == "Code"


class TestGetSkill:
    """Tests for get_skill with custom skill fallback."""

    def test_builtin(self) -> None:
        assert get_skill("code") is not None
        assert get_skill("code").name == "Code"

    def test_unknown(self) -> None:
        assert get_skill("nonexistent_skill_xyz") is None


class TestSkillEditorValidation:
    """Tests for validate_skill_fields."""

    def test_valid(self) -> None:
        from emily_chat.ui.skill_editor import validate_skill_fields
        assert validate_skill_fields("My Skill", "\U0001f680", "A description") == []

    def test_empty_name(self) -> None:
        from emily_chat.ui.skill_editor import validate_skill_fields
        errors = validate_skill_fields("", "\U0001f680", "desc")
        assert any("Name" in e for e in errors)

    def test_long_name(self) -> None:
        from emily_chat.ui.skill_editor import validate_skill_fields
        errors = validate_skill_fields("x" * 31, "\U0001f680", "desc")
        assert any("30" in e for e in errors)

    def test_empty_icon(self) -> None:
        from emily_chat.ui.skill_editor import validate_skill_fields
        errors = validate_skill_fields("Name", "", "desc")
        assert any("Icon" in e for e in errors)

    def test_empty_description(self) -> None:
        from emily_chat.ui.skill_editor import validate_skill_fields
        errors = validate_skill_fields("Name", "\U0001f680", "")
        assert any("Description" in e for e in errors)
