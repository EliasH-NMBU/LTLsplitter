from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ltlsplitter.core.llm_split import split_requirement
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage


class RequirementSplitPage(WizardPage):
    title = "1. Requirement Splitting"
    description = (
        "Enter a natural-language requirement. An LLM can propose a split into sub-requirements "
        "(e.g. r1.1 ∧ r1.2 ⇒ R1), or you can add/edit sub-requirements manually. Either way, "
        "review the list below before moving on — it's what stage 3 authors specs against."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)

        self.requirement_edit = QPlainTextEdit(self.state.original_requirement)
        self.requirement_edit.setPlaceholderText("The system shall ...")
        self.requirement_edit.textChanged.connect(self._on_requirement_text_changed)
        self.content_layout.addWidget(self.requirement_edit)

        self.split_button = QPushButton("Split with LLM")
        self.split_button.clicked.connect(self._on_split_clicked)
        self.content_layout.addWidget(self.split_button)

        self.content_layout.addWidget(QLabel("Sub-requirements:"))
        self.sub_requirement_list = QListWidget()
        self.sub_requirement_list.addItems(self.state.sub_requirements)
        self.content_layout.addWidget(self.sub_requirement_list)

        add_row = QHBoxLayout()
        self.new_sub_requirement_edit = QLineEdit()
        self.new_sub_requirement_edit.setPlaceholderText("New sub-requirement text")
        self.new_sub_requirement_edit.returnPressed.connect(self._on_add_sub_requirement)
        add_button = QPushButton("Add")
        add_button.clicked.connect(self._on_add_sub_requirement)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(self._on_remove_selected)
        add_row.addWidget(self.new_sub_requirement_edit)
        add_row.addWidget(add_button)
        add_row.addWidget(remove_button)
        self.content_layout.addLayout(add_row)

    def _on_requirement_text_changed(self) -> None:
        self.state.original_requirement = self.requirement_edit.toPlainText()

    def _on_split_clicked(self) -> None:
        if not self.state.original_requirement.strip():
            QMessageBox.warning(self, "No requirement", "Enter a requirement first.")
            return
        try:
            result = split_requirement(self.state.original_requirement)
        except NotImplementedError:
            QMessageBox.information(
                self,
                "Not implemented yet",
                "LLM-based splitting isn't wired up yet — add sub-requirements manually below for now.",
            )
            return
        self.state.sub_requirements = list(result.sub_requirements)
        self.sub_requirement_list.clear()
        self.sub_requirement_list.addItems(self.state.sub_requirements)

    def _on_add_sub_requirement(self) -> None:
        text = self.new_sub_requirement_edit.text().strip()
        if not text:
            return
        self.state.sub_requirements.append(text)
        self.sub_requirement_list.addItem(text)
        self.new_sub_requirement_edit.clear()

    def _on_remove_selected(self) -> None:
        for item in self.sub_requirement_list.selectedItems():
            row = self.sub_requirement_list.row(item)
            self.sub_requirement_list.takeItem(row)
            del self.state.sub_requirements[row]
