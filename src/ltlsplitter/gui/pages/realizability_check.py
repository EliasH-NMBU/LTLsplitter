from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from ltlsplitter.core.kind2_check import check_realizability_kind2
from ltlsplitter.core.models import RealizabilityResult, Specification, VariableRole
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.realizability import ToolNotFoundError, check_realizability
from ltlsplitter.gui.pages.base import WizardPage


class RealizabilityCheckPage(WizardPage):
    title = "3. Realizability Check"
    description = (
        "Checks whether a system strategy exists that satisfies the accepted formula(s) "
        "together with every other requirement already in the imported FRET file, against any "
        "adversarial sequence of input values -- the 'combined back with the entire system' "
        "check. Strix (game synthesis, future-time LTL) and Kind2 (SMT/k-induction contract "
        "analysis, understands typed variables natively) run side by side as a cross-check."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)

        check_button = QPushButton("Check Realizability (combined with system)")
        check_button.clicked.connect(self._on_check_clicked)
        self.content_layout.addWidget(check_button)

        self.content_layout.addWidget(QLabel("Strix:"))
        self.strix_label = QLabel()
        self.strix_label.setWordWrap(True)
        self.content_layout.addWidget(self.strix_label)

        self.content_layout.addWidget(QLabel("Kind2:"))
        self.kind2_label = QLabel()
        self.kind2_label.setWordWrap(True)
        self.content_layout.addWidget(self.kind2_label)

        self.content_layout.addStretch()

    def on_show(self) -> None:
        strix_result = self.state.realizability_results.get("Strix")
        kind2_result = self.state.realizability_results.get("Kind2")
        self._render(self.strix_label, strix_result)
        self._render(self.kind2_label, kind2_result)

    @staticmethod
    def _render(label: QLabel, result: RealizabilityResult | None) -> None:
        if result is None:
            label.setStyleSheet("")
            label.setText("(not checked yet)")
        elif result.realizable:
            label.setStyleSheet("color: #1a7f37;")
            label.setText("Realizable: a satisfying strategy exists." + (f" {result.details}" if result.details else ""))
        else:
            label.setStyleSheet("color: #b00020;")
            counterexample = f" Counterexample: {result.counterexample}" if result.counterexample else ""
            label.setText(f"Not realizable. {result.details}{counterexample}".strip())

    def _on_check_clicked(self) -> None:
        if self.state.fret_import is None or not self.state.selected_requirement_id:
            QMessageBox.information(self, "Nothing to check", "Import a FRET file and select a requirement on page 1 first.")
            return

        sub_formulas = self.state.active_sub_formulas()
        other_requirements = [
            req for req in self.state.fret_import.requirements if req.reqid != self.state.selected_requirement_id
        ]

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

        # Strix only parses future-time LTL (G/F/X/U) -- past-time H/O/S/Y (what the pt forms
        # use) isn't accepted by its grammar, confirmed empirically against the installed
        # binary -- so Strix's check is built from the ft forms, not pt.
        ft_formulas = [s.ft_formula for s in sub_formulas] + [r.ft_formula for r in other_requirements]
        combined = " & ".join(f"({f})" for f in ft_formulas)
        spec = Specification(requirement_id=self.state.selected_requirement_id, ltl_formula=combined)
        try:
            strix_result = check_realizability(spec, inputs, outputs)
        except ToolNotFoundError as exc:
            strix_result = RealizabilityResult(realizable=False, details=str(exc))
        except Exception as exc:  # noqa: BLE001 -- surface any Strix subprocess/parse failure
            strix_result = RealizabilityResult(realizable=False, details=f"Check failed: {exc}")

        # Kind2 has no built-in past-time operator -- its check compiles the pt (H-wrapped)
        # forms by hand into a Lustre ghost variable, so it needs pt, not ft.
        pt_formulas = [s.pt_formula for s in sub_formulas] + [r.pt_formula for r in other_requirements]
        try:
            kind2_result = check_realizability_kind2(pt_formulas, variables)
        except Exception as exc:  # noqa: BLE001 -- surface any kind2 subprocess/parse failure
            kind2_result = RealizabilityResult(realizable=False, details=f"Check failed: {exc}")

        self.state.realizability_results = {"Strix": strix_result, "Kind2": kind2_result}
        self._render(self.strix_label, strix_result)
        self._render(self.kind2_label, kind2_result)
