"""Emily Editor dialog — build system profiles (role-to-model mappings)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from emily_chat.models.registry import EMILY_MODEL_REGISTRY, get_model
from emily_chat.profiles import (
    EMILY_PROFILE_ROLES,
    EmilyProfile,
    get_profile,
    load_profiles,
    save_profiles,
)

if TYPE_CHECKING:
    from emily_chat.config import AppSettings


def _all_model_keys() -> list[tuple[str, str]]:
    """Return [(registry_key, display_name), ...] for all models, sorted by display."""
    items: list[tuple[str, str]] = [("auto", "Auto (smart routing)")]
    for key, spec in sorted(
        EMILY_MODEL_REGISTRY.items(),
        key=lambda p: (p[1].display, p[0]),
    ):
        items.append((key, spec.display))
    return items


class EmilyEditorDialog(QDialog):
    """Dialog to create and edit Emily system profiles (role -> model)."""

    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Emily Editor — System Profiles")
        self.setMinimumSize(580, 420)
        self._profiles = load_profiles()
        self._dirty = False
        self._build_ui()
        self._refresh_profile_list()
        self._select_profile_by_id(settings.active_profile_id)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        # Left: profile list
        left = QVBoxLayout()
        left_group = QGroupBox("Profiles")
        left_inner = QVBoxLayout(left_group)
        self._profile_list = QListWidget()
        self._profile_list.setMinimumWidth(160)
        self._profile_list.currentItemChanged.connect(self._on_profile_selected)
        left_inner.addWidget(self._profile_list)
        btn_row = QHBoxLayout()
        btn_row.addWidget(QPushButton("New", clicked=self._new_profile))
        btn_row.addWidget(QPushButton("Duplicate", clicked=self._duplicate_profile))
        btn_row.addWidget(QPushButton("Delete", clicked=self._delete_profile))
        left_inner.addLayout(btn_row)
        left.addWidget(left_group)
        layout.addLayout(left)

        # Right: role -> model for selected profile
        right = QVBoxLayout()
        right_group = QGroupBox("Role → Model")
        self._form = QFormLayout(right_group)
        self._role_combos: dict[str, QComboBox] = {}
        model_items = _all_model_keys()
        for role_key, role_label in EMILY_PROFILE_ROLES:
            combo = QComboBox()
            for key, display in model_items:
                combo.addItem(display, key)
            combo.currentIndexChanged.connect(lambda: self._mark_dirty())
            self._role_combos[role_key] = combo
            self._form.addRow(role_label, combo)
        right.addWidget(right_group)
        self._profile_name_edit = QLineEdit()
        self._profile_name_edit.setPlaceholderText("Profile name")
        self._profile_name_edit.textChanged.connect(lambda: self._mark_dirty())
        self._form.addRow(QLabel("Name"), self._profile_name_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Close,
        )
        apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.clicked.connect(self._apply_profile)
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_btn.clicked.connect(self._save_profiles)
        export_btn = QPushButton("Export to voice config")
        export_btn.clicked.connect(self._export_to_voice_config)
        buttons.addButton(export_btn, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        layout.addLayout(right)

    def _mark_dirty(self) -> None:
        self._dirty = True

    def _refresh_profile_list(self) -> None:
        self._profile_list.clear()
        for p in self._profiles:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            self._profile_list.addItem(item)

    def _select_profile_by_id(self, profile_id: str) -> None:
        for i in range(self._profile_list.count()):
            item = self._profile_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == profile_id:
                self._profile_list.setCurrentItem(item)
                return

    def _current_profile_id(self) -> str | None:
        item = self._profile_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _populate_form(self, profile: EmilyProfile | None) -> None:
        for combo in self._role_combos.values():
            combo.blockSignals(True)
        try:
            if profile is None:
                for combo in self._role_combos.values():
                    combo.setCurrentIndex(0)
                self._profile_name_edit.clear()
                self._dirty = False
                return
            self._profile_name_edit.setText(profile.name)
            for role_key, combo in self._role_combos.items():
                model_key = profile.roles.get(role_key, "auto")
                idx = combo.findData(model_key)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.setCurrentIndex(0)
            self._dirty = False
        finally:
            for combo in self._role_combos.values():
                combo.blockSignals(False)

    def _on_profile_selected(self) -> None:
        pid = self._current_profile_id()
        profile = get_profile(self._profiles, pid) if pid else None
        self._populate_form(profile)

    def _collect_form_into_profile(self, profile_id: str) -> EmilyProfile:
        roles = {}
        for role_key, combo in self._role_combos.items():
            roles[role_key] = combo.currentData() or "auto"
        name = self._profile_name_edit.text().strip() or "Unnamed"
        return EmilyProfile(id=profile_id, name=name, roles=roles)

    def _new_profile(self) -> None:
        new_id = "profile-" + uuid.uuid4().hex[:8]
        new_profile = EmilyProfile(
            id=new_id,
            name="New Profile",
            roles={role: "auto" for role, _ in EMILY_PROFILE_ROLES},
        )
        self._profiles.append(new_profile)
        self._refresh_profile_list()
        self._select_profile_by_id(new_id)
        self._populate_form(new_profile)
        self._mark_dirty()

    def _duplicate_profile(self) -> None:
        pid = self._current_profile_id()
        if not pid:
            return
        source = get_profile(self._profiles, pid)
        if not source:
            return
        new_id = "profile-" + uuid.uuid4().hex[:8]
        copy = EmilyProfile(id=new_id, name=source.name + " (copy)", roles=dict(source.roles))
        self._profiles.append(copy)
        self._refresh_profile_list()
        self._select_profile_by_id(new_id)
        self._populate_form(copy)
        self._mark_dirty()

    def _delete_profile(self) -> None:
        pid = self._current_profile_id()
        if not pid or pid == "default":
            QMessageBox.information(
                self,
                "Emily Editor",
                "The Default profile cannot be deleted.",
            )
            return
        if (
            QMessageBox.question(
                self,
                "Emily Editor",
                "Delete this profile?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self._profiles = [p for p in self._profiles if p.id != pid]
        self._refresh_profile_list()
        if self._profiles:
            self._profile_list.setCurrentRow(0)
        self._mark_dirty()

    def _apply_profile(self) -> None:
        pid = self._current_profile_id()
        if not pid:
            return
        profile = self._collect_form_into_profile(pid)
        existing = get_profile(self._profiles, pid)
        if existing:
            idx = next(i for i, p in enumerate(self._profiles) if p.id == pid)
            self._profiles[idx] = profile
        self._settings.active_profile_id = pid
        self._settings.save()
        QMessageBox.information(
            self,
            "Emily Editor",
            f"Applied profile: {profile.name}",
        )

    def _save_profiles(self) -> None:
        pid = self._current_profile_id()
        if pid:
            profile = self._collect_form_into_profile(pid)
            existing = get_profile(self._profiles, pid)
            if existing:
                idx = next(i for i, p in enumerate(self._profiles) if p.id == pid)
                self._profiles[idx] = profile
        save_profiles(self._profiles)
        self._dirty = False
        item = self._profile_list.currentItem()
        if item and pid:
            p = get_profile(self._profiles, pid)
            if p:
                item.setText(p.name)
        QMessageBox.information(
            self,
            "Emily Editor",
            "Profiles saved.",
        )

    def _find_config_path(self) -> Path | None:
        """Return path to main Emily config.yaml."""
        import os

        env_path = os.environ.get("EMILY_CONFIG_PATH")
        if env_path:
            p = Path(env_path)
            if p.exists():
                return p
        cwd = Path.cwd() / "config.yaml"
        if cwd.exists():
            return cwd
        root = Path(__file__).resolve().parents[2] / "config.yaml"
        return root if root.exists() else None

    def _export_to_voice_config(self) -> None:
        """Export current profile to main Emily config.yaml (voice system)."""
        config_path = self._find_config_path()
        if not config_path:
            QMessageBox.warning(
                self,
                "Emily Editor",
                "config.yaml not found. Set EMILY_CONFIG_PATH or run from project root.",
            )
            return
        pid = self._current_profile_id()
        if not pid:
            return
        profile = self._collect_form_into_profile(pid)
        # Map profile roles to main config tiers (voice Emily)
        role_to_tier: dict[str, str] = {
            "core": "fast",
            "coding": "smart",
            "research": "smart",
            "writing": "smart",
            "reasoning": "reasoning",
            "fast": "fast",
        }
        reply = QMessageBox.question(
            self,
            "Emily Editor",
            f'Export profile "{profile.name}" to voice config?\n\n'
            f"Backup will be saved as {config_path}.bak",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from datetime import datetime

            import yaml

            raw = yaml.safe_load(config_path.read_text()) or {}
            backup_path = (
                config_path.parent
                / f"{config_path.name}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            )
            backup_path.write_text(config_path.read_text(), encoding="utf-8")
            llm = raw.setdefault("llm", {})
            models = llm.setdefault("models", {})
            for role, tier in role_to_tier.items():
                model_key = profile.roles.get(role, "auto")
                if model_key == "auto":
                    continue
                spec = get_model(model_key)
                if spec is None:
                    continue
                if spec.provider == "ollama":
                    models[tier] = spec.model_id
                elif spec.provider == "llamacpp":
                    llm.setdefault("tier_backend", {})[tier] = "llamacpp"
            config_path.write_text(
                yaml.dump(raw, default_flow_style=False, sort_keys=False), encoding="utf-8"
            )
            QMessageBox.information(
                self,
                "Emily Editor",
                f"Exported to {config_path}\nBackup: {backup_path.name}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Emily Editor",
                f"Export failed: {e}",
            )
