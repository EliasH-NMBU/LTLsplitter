from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ltlsplitter.core.models import Specification, VariableRole
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.realizability import ToolNotFoundError, check_consistency, check_realizability
from ltlsplitter.gui.pages.base import WizardPage


class ConsistencyCheckPage(WizardPage):
    title = "4. Consistency & Realizability Check"
    description = (
        "Verify the requirement set is satisfiable and realizable before generating monitors. "
        "Conflicting requirements are reported here rather than failing silently downstream."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._current_requirement_id: str | None = None

        body = QHBoxLayout()

        left = QVBoxLayout()
        left.addWidget(QLabel("Requirements with specs:"))
        self.requirement_list = QListWidget()
        self.requirement_list.itemSelectionChanged.connect(self._on_requirement_selected)
        left.addWidget(self.requirement_list)
        body.addLayout(left, 1)

        right = QVBoxLayout()

        consistency_button = QPushButton("Check Consistency (all requirements)")
        consistency_button.clicked.connect(self._on_check_consistency_clicked)
        right.addWidget(consistency_button)

        self.consistency_label = QLabel()
        self.consistency_label.setWordWrap(True)
        right.addWidget(self.consistency_label)

        right.addSpacing(12)

        realizability_button = QPushButton("Check Realizability (selected requirement)")
        realizability_button.clicked.connect(self._on_check_realizability_clicked)
        right.addWidget(realizability_button)

        self.realizability_label = QLabel()
        self.realizability_label.setWordWrap(True)
        right.addWidget(self.realizability_label)

        right.addStretch()
        body.addLayout(right, 1)
        self.content_layout.addLayout(body)

    def on_show(self) -> None:
        self._refresh_requirement_list()

    def _specs_with_formulas(self) -> list[Specification]:
        specs = []
        for requirement_id in self.state.requirement_ids():
            spec = self.state.specifications.get(requirement_id)
            if spec and spec.ltl_formula and spec.ltl_formula.strip():
                specs.append(spec)
        return specs

    def _refresh_requirement_list(self) -> None:
        previously_selected = self._current_requirement_id

        self.requirement_list.blockSignals(True)
        self.requirement_list.clear()
        for spec in self._specs_with_formulas():
            item = QListWidgetItem(f"{spec.requirement_id}: {spec.ltl_formula}")
            item.setData(Qt.ItemDataRole.UserRole, spec.requirement_id)
            self.requirement_list.addItem(item)
        self.requirement_list.blockSignals(False)

        if self.requirement_list.count() == 0:
            self._current_requirement_id = None
            return

        target_row = 0
        for row in range(self.requirement_list.count()):
            if self.requirement_list.item(row).data(Qt.ItemDataRole.UserRole) == previously_selected:
                target_row = row
                break
        self.requirement_list.setCurrentRow(target_row)

    def _on_requirement_selected(self) -> None:
        items = self.requirement_list.selectedItems()
        if not items:
            self._current_requirement_id = None
            return
        self._current_requirement_id = items[0].data(Qt.ItemDataRole.UserRole)
        self.realizability_label.clear()

    def _on_check_consistency_clicked(self) -> None:
        specs = self._specs_with_formulas()
        if not specs:
            QMessageBox.information(
                self, "No specs", "Author at least one LTL formula in stage 3 first."
            )
            return
        try:
            result = check_consistency(specs, self.state.variables)
        except ToolNotFoundError as exc:
            self.consistency_label.setStyleSheet("color: #666;")
            self.consistency_label.setText(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- surface any nuXmv subprocess/parse failure
            self.consistency_label.setStyleSheet("color: #b00020;")
            self.consistency_label.setText(f"Check failed: {exc}")
            return
        if result.consistent:
            self.consistency_label.setStyleSheet("color: #1a7f37;")
            self.consistency_label.setText("Consistent: all requirements can hold simultaneously.")
        else:
            self.consistency_label.setStyleSheet("color: #b00020;")
            conflicts = ", ".join(result.conflicting_requirement_ids) or "unknown"
            self.consistency_label.setText(
                f"Inconsistent -- conflicting requirements: {conflicts}. {result.details}".strip()
            )

    def _on_check_realizability_clicked(self) -> None:
        if self._current_requirement_id is None:
            QMessageBox.information(self, "No requirement selected", "Select a requirement on the left.")
            return
        spec = self.state.specifications.get(self._current_requirement_id)
        if spec is None or not spec.ltl_formula:
            QMessageBox.information(self, "No spec", "Author an LTL formula for this requirement in stage 3 first.")
            return
        inputs = [v.name for v in self.state.variables if v.role == VariableRole.INPUT]
        outputs = [v.name for v in self.state.variables if v.role == VariableRole.OUTPUT]
        if not outputs:
            QMessageBox.information(
                self,
                "No output variables",
                "Mark at least one variable as 'output' in stage 2 -- realizability checks "
                "whether the system side can satisfy the spec against any input from the environment.",
            )
            return
        try:
            result = check_realizability(spec, inputs, outputs)
        except ToolNotFoundError as exc:
            self.realizability_label.setStyleSheet("color: #666;")
            self.realizability_label.setText(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- surface any Strix subprocess/parse failure
            self.realizability_label.setStyleSheet("color: #b00020;")
            self.realizability_label.setText(f"Check failed: {exc}")
            return
        if result.realizable:
            self.realizability_label.setStyleSheet("color: #1a7f37;")
            self.realizability_label.setText("Realizable: a satisfying strategy exists.")
        else:
            self.realizability_label.setStyleSheet("color: #b00020;")
            counterexample = f" Counterexample: {result.counterexample}" if result.counterexample else ""
            self.realizability_label.setText(f"Not realizable. {result.details}{counterexample}".strip())
