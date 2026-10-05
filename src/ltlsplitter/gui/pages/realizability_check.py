from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from ltlsplitter.core.models import Specification, VariableRole
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.realizability import ToolNotFoundError, check_realizability
from ltlsplitter.gui.pages.base import WizardPage


class RealizabilityCheckPage(WizardPage):
    title = "3. Realizability Check"
    description = (
        "Checks whether a system strategy exists that satisfies the accepted formula(s) "
        "(future-time form -- Strix doesn't parse past-time LTL) together with every other "
        "requirement already in the imported FRET file, against any adversarial sequence of "
        "input values -- the 'combined back with the entire system' check."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)

        check_button = QPushButton("Check Realizability (combined with system)")
        check_button.clicked.connect(self._on_check_clicked)
        self.content_layout.addWidget(check_button)

        self.result_label = QLabel()
        self.result_label.setWordWrap(True)
        self.content_layout.addWidget(self.result_label)

        self.content_layout.addStretch()

    def on_show(self) -> None:
        if self.state.realizability_result is not None:
            self._render(self.state.realizability_result)
        else:
            self.result_label.setText("(not checked yet)")

    def _render(self, result) -> None:
        if result.realizable:
            self.result_label.setStyleSheet("color: #1a7f37;")
            self.result_label.setText("Realizable: a satisfying strategy exists.")
        else:
            self.result_label.setStyleSheet("color: #b00020;")
            counterexample = f" Counterexample: {result.counterexample}" if result.counterexample else ""
            self.result_label.setText(f"Not realizable. {result.details}{counterexample}".strip())

    def _on_check_clicked(self) -> None:
        if self.state.fret_import is None or not self.state.selected_requirement_id:
            QMessageBox.information(self, "Nothing to check", "Import a FRET file and select a requirement on page 1 first.")
            return

        sub_formulas = self.state.active_sub_formulas()
        other_formulas = [
            req.ft_formula
            for req in self.state.fret_import.requirements
            if req.reqid != self.state.selected_requirement_id
        ]
        # Strix only parses future-time LTL (G/F/X/U) -- past-time H/O/S/Y (what the pt forms
        # use) isn't accepted by its grammar, confirmed empirically against the installed
        # binary -- so the realizability check is built from the ft forms, not pt.
        all_formulas = [s.ft_formula for s in sub_formulas] + other_formulas
        combined = " & ".join(f"({f})" for f in all_formulas)
        spec = Specification(requirement_id=self.state.selected_requirement_id, ltl_formula=combined)

        variables = self.state.fret_import.variables
        inputs = [v.name for v in variables if v.role == VariableRole.INPUT]
        outputs = [v.name for v in variables if v.role == VariableRole.OUTPUT]
        if not outputs:
            QMessageBox.information(
                self, "No output variables",
                "The imported FRET file has no Output-role variables -- realizability checks "
                "whether the system side can satisfy the spec against any input from the environment.",
            )
            return

        try:
            result = check_realizability(spec, inputs, outputs)
        except ToolNotFoundError as exc:
            self.result_label.setStyleSheet("color: #666;")
            self.result_label.setText(str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- surface any Strix subprocess/parse failure
            self.result_label.setStyleSheet("color: #b00020;")
            self.result_label.setText(f"Check failed: {exc}")
            return

        self.state.realizability_result = result
        self._render(result)
