from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.reference_check import find_undeclared_references
from ltlsplitter.gui.pages.base import WizardPage


class SpecAuthoringPage(WizardPage):
    title = "3. Spec Authoring"
    description = "Author an LTL formula or behavior tree over the declared variables for each sub-requirement."

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._current_requirement_id: str | None = None

        body = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Requirements:"))
        self.requirement_list = QListWidget()
        self.requirement_list.itemSelectionChanged.connect(self._on_requirement_selected)
        left.addWidget(self.requirement_list)
        body.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel("LTL formula:"))
        self.formula_edit = QPlainTextEdit()
        self.formula_edit.setPlaceholderText("G (request -> F response)")
        self.formula_edit.textChanged.connect(self._on_formula_changed)
        right.addWidget(self.formula_edit)

        right.addWidget(QLabel("Declared variables:"))
        self.variables_label = QLabel()
        self.variables_label.setWordWrap(True)
        right.addWidget(self.variables_label)

        validate_button = QPushButton("Validate References")
        validate_button.clicked.connect(self._on_validate_clicked)
        right.addWidget(validate_button)

        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        right.addWidget(self.validation_label)

        body.addLayout(right, 2)
        self.content_layout.addLayout(body)

    def on_show(self) -> None:
        self._refresh_requirement_list()
        self._refresh_variables_label()

    def _refresh_requirement_list(self) -> None:
        previously_selected = self._current_requirement_id

        self.requirement_list.blockSignals(True)
        self.requirement_list.clear()
        for requirement_id in self.state.requirement_ids():
            text = self.state.requirement_text(requirement_id)
            item = QListWidgetItem(f"{requirement_id}: {text}")
            item.setData(Qt.ItemDataRole.UserRole, requirement_id)
            self.requirement_list.addItem(item)
        self.requirement_list.blockSignals(False)

        if self.requirement_list.count() == 0:
            self._current_requirement_id = None
            self.formula_edit.blockSignals(True)
            self.formula_edit.clear()
            self.formula_edit.blockSignals(False)
            return

        target_row = 0
        for row in range(self.requirement_list.count()):
            if self.requirement_list.item(row).data(Qt.ItemDataRole.UserRole) == previously_selected:
                target_row = row
                break
        self.requirement_list.setCurrentRow(target_row)

    def _refresh_variables_label(self) -> None:
        if self.state.variables:
            self.variables_label.setText(", ".join(v.name for v in self.state.variables))
        else:
            self.variables_label.setText("(none declared yet — go back to stage 2)")

    def _on_requirement_selected(self) -> None:
        items = self.requirement_list.selectedItems()
        if not items:
            return
        requirement_id = items[0].data(Qt.ItemDataRole.UserRole)
        self._current_requirement_id = requirement_id
        formula = self.state.spec_for(requirement_id).ltl_formula or ""
        self.formula_edit.blockSignals(True)
        self.formula_edit.setPlainText(formula)
        self.formula_edit.blockSignals(False)
        self.validation_label.clear()

    def _on_formula_changed(self) -> None:
        if self._current_requirement_id is None:
            return
        self.state.spec_for(self._current_requirement_id).ltl_formula = self.formula_edit.toPlainText()

    def _on_validate_clicked(self) -> None:
        if self._current_requirement_id is None:
            QMessageBox.information(self, "No requirement selected", "Add a requirement in stage 1 first.")
            return
        declared_names = {v.name for v in self.state.variables}
        undeclared = find_undeclared_references(self.formula_edit.toPlainText(), declared_names)
        if undeclared:
            self.validation_label.setStyleSheet("color: #b00020;")
            self.validation_label.setText("Possibly undeclared: " + ", ".join(undeclared))
        else:
            self.validation_label.setStyleSheet("color: #1a7f37;")
            self.validation_label.setText("All referenced identifiers are declared variables.")
