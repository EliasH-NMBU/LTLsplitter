from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from ltlsplitter.core.kind2_check import check_realizability_kind2
from ltlsplitter.core.models import RealizabilityResult, VariableRole
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.core.realizability import ToolNotFoundError, check_realizability_typed
from ltlsplitter.gui.pages.base import WizardPage
from ltlsplitter.gui.theme import compact


class RealizabilityCheckPage(WizardPage):
    title = "3. Realizability Check"
    description = (
        "Checks whether a system strategy exists that satisfies the entire current system -- "
        "every requirement in the imported FRET file, counted exactly once (a split's "
        "sub-formulas once saved stand in for the original they came from, since stage 2 "
        "already proved they're equivalent to it) -- against any adversarial sequence of input "
        "values. Requirements marked as assumptions (page 1's checkbox) are treated as "
        "environment constraints (A -> G) rather than system guarantees. Strix (game synthesis, "
        "future-time LTL) and Kind2 (SMT/k-induction contract analysis, understands typed "
        "variables natively) run side by side as a cross-check."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)

        check_button = compact(QPushButton("Check Realizability (entire system)"))
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
        if self.state.fret_import is None or not self.state.fret_import.requirements:
            QMessageBox.information(self, "Nothing to check", "Import a FRET file on page 1 first.")
            return

        leaves = self.state.fret_import.leaf_requirements()
        variables = self.state.fret_import.variables
        if not any(v.role == VariableRole.OUTPUT for v in variables):
            QMessageBox.information(
                self, "No output variables",
                "The imported FRET file has no Output-role variables -- realizability checks "
                "whether the system side can satisfy the spec against any input from the environment.",
            )
            return

        # Leaf requirements marked as environment assumptions (is_assumption) must not be
        # guaranteed by the system -- they're constraints the environment is assumed to respect,
        # not obligations the system controls (e.g. "classifier is in {0,1,2}" when classifier is
        # an input). Flat-ANDing them in as guarantees makes synthesis fail on formulas the
        # system never had a chance to satisfy on its own.
        assumption_leaves = [r for r in leaves if r.is_assumption]
        guarantee_leaves = [r for r in leaves if not r.is_assumption]

        # Strix only parses future-time LTL (G/F/X/U) -- past-time H/O/S/Y (what the pt forms
        # use) isn't accepted by its grammar, confirmed empirically against the installed
        # binary -- so Strix's check is built from the ft forms, not pt. check_realizability_typed
        # additionally abstracts any typed "variable OP literal" comparisons into fresh boolean
        # propositions first, since Strix's grammar (like Spot's/SPIN's) only accepts bare
        # identifiers as atomic propositions -- see its docstring for why.
        combined_guarantees_ft = " & ".join(f"({r.ft_formula})" for r in guarantee_leaves) or "true"
        if assumption_leaves:
            combined_assumptions_ft = " & ".join(f"({r.ft_formula})" for r in assumption_leaves)
            combined_ft = f"({combined_assumptions_ft}) -> ({combined_guarantees_ft})"
        else:
            combined_ft = combined_guarantees_ft
        try:
            strix_result = check_realizability_typed(combined_ft, variables, self.state.fret_import.project)
        except ToolNotFoundError as exc:
            strix_result = RealizabilityResult(realizable=False, details=str(exc))
        except Exception as exc:  # noqa: BLE001 -- surface any Strix subprocess/parse failure
            strix_result = RealizabilityResult(realizable=False, details=f"Check failed: {exc}")

        # Kind2 has no built-in past-time operator -- its check compiles the pt (H-wrapped)
        # forms by hand into a Lustre ghost variable, so it needs pt, not ft.
        assumption_pt_formulas = [r.pt_formula for r in assumption_leaves]
        guarantee_pt_formulas = [r.pt_formula for r in guarantee_leaves]
        try:
            kind2_result = check_realizability_kind2(assumption_pt_formulas, guarantee_pt_formulas, variables)
        except Exception as exc:  # noqa: BLE001 -- surface any kind2 subprocess/parse failure
            kind2_result = RealizabilityResult(realizable=False, details=f"Check failed: {exc}")

        self.state.realizability_results = {"Strix": strix_result, "Kind2": kind2_result}
        self._render(self.strix_label, strix_result)
        self._render(self.kind2_label, kind2_result)
