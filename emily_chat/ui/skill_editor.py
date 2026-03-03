"""Custom skill editor dialog.

Provides a form for creating and editing user-defined skills that
persist to ``~/.emily-chat/custom_skills.json``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from emily_chat.emily.skills import EmilySkill


def validate_skill_fields(
    name: str,
    icon: str,
    description: str,
) -> list[str]:
    """Validate custom skill form fields.

    Args:
        name: Skill name.
        icon: Emoji icon string.
        description: Short description.

    Returns:
        List of error messages; empty if valid.
    """
    errors: list[str] = []
    if not name.strip():
        errors.append("Name is required.")
    if len(name.strip()) > 30:
        errors.append("Name must be 30 characters or fewer.")
    if not icon.strip():
        errors.append("Icon is required.")
    if len(icon.strip()) > 4:
        errors.append("Icon must be a single emoji.")
    if not description.strip():
        errors.append("Description is required.")
    return errors


class SkillEditorDialog(QDialog):
    """Dialog for creating or editing a custom Emily skill.

    Args:
        skill: An existing :class:`EmilySkill` to edit, or ``None``
            to create a new one.
        parent: Parent widget.
    """

    def __init__(
        self,
        skill: EmilySkill | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("skillEditorDialog")
        self.setWindowTitle("Custom Skill Editor")
        self.setMinimumWidth(420)
        self.setModal(True)

        self._result_skill: EmilySkill | None = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Legal Review")
        form.addRow("Name:", self._name_edit)

        self._icon_edit = QLineEdit()
        self._icon_edit.setPlaceholderText("e.g. \u2696\ufe0f")
        self._icon_edit.setMaximumWidth(60)
        form.addRow("Icon:", self._icon_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Short description of what this skill does")
        form.addRow("Description:", self._desc_edit)

        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlaceholderText(
            "System prompt addition (injected before the conversation)"
        )
        self._prompt_edit.setMaximumHeight(120)
        form.addRow("System Prompt:", self._prompt_edit)

        temp_row = QHBoxLayout()
        self._temp_slider = QSlider(Qt.Orientation.Horizontal)
        self._temp_slider.setRange(0, 100)
        self._temp_slider.setValue(50)
        self._temp_label = QLabel("0.50")
        self._temp_slider.valueChanged.connect(lambda v: self._temp_label.setText(f"{v / 100:.2f}"))
        temp_row.addWidget(self._temp_slider)
        temp_row.addWidget(self._temp_label)
        form.addRow("Temperature:", temp_row)

        self._thinking_cb = QCheckBox("Enable extended thinking")
        form.addRow("", self._thinking_cb)

        self._web_search_cb = QCheckBox("Enable web search")
        form.addRow("", self._web_search_cb)

        self._code_exec_cb = QCheckBox("Enable code execution")
        form.addRow("", self._code_exec_cb)

        layout.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #ef4444; font-size: 12px;")
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

        if skill is not None:
            self._populate(skill)

    def _populate(self, skill: EmilySkill) -> None:
        """Fill form fields from an existing skill.

        Args:
            skill: The skill to load into the editor.
        """
        self._name_edit.setText(skill.name)
        self._icon_edit.setText(skill.icon)
        self._desc_edit.setText(skill.description)
        self._prompt_edit.setPlainText(skill.system_addition)
        self._temp_slider.setValue(int(skill.temperature * 100))
        self._thinking_cb.setChecked(skill.enable_thinking)
        self._web_search_cb.setChecked(skill.enable_web_search)
        self._code_exec_cb.setChecked(skill.enable_code_execution)

    def _on_save(self) -> None:
        """Validate and build the skill."""
        name = self._name_edit.text()
        icon = self._icon_edit.text()
        desc = self._desc_edit.text()

        errors = validate_skill_fields(name, icon, desc)
        if errors:
            self._error_label.setText("\n".join(errors))
            self._error_label.setVisible(True)
            return

        self._result_skill = EmilySkill(
            name=name.strip(),
            icon=icon.strip(),
            description=desc.strip(),
            system_addition=self._prompt_edit.toPlainText().strip(),
            temperature=self._temp_slider.value() / 100,
            enable_thinking=self._thinking_cb.isChecked(),
            enable_web_search=self._web_search_cb.isChecked(),
            enable_code_execution=self._code_exec_cb.isChecked(),
        )
        self.accept()

    def get_skill(self) -> EmilySkill | None:
        """Return the created/edited skill, or ``None`` if cancelled."""
        return self._result_skill
