from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout

from ltlsplitter.core.equivalence_check import validate_decomposition
from ltlsplitter.core.llm_decompose import MissingAPIKeyError, decompose
from ltlsplitter.core.models import FretRequirement, ToolCheckResult
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.base import WizardPage
from ltlsplitter.gui.theme import compact

_SETTINGS_ORG = "LTLsplitter"
_SETTINGS_APP = "LTLsplitter"
_API_KEY_SETTING = "anthropic/api_key"


class DecompositionValidationPage(WizardPage):
    title = "2. Decomposition Validation"
    description = (
        "nuXmv, Spot, and SPIN each independently check that the sub-formulas' conjunction is "
        "logically equivalent to the original requirement, and that no single sub-formula is -- "
        "by itself -- already equivalent to the whole original."
    )

    def __init__(self, state: ProjectState, parent=None):
        super().__init__(state, parent)
        self._settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)

        validate_button = compact(QPushButton("Validate Decomposition"))
        validate_button.clicked.connect(self._on_validate_clicked)
        self.content_layout.addWidget(validate_button)

        self.content_layout.addWidget(QLabel("What's being tested:"))
        self.what_is_tested_label = QLabel()
        self.what_is_tested_label.setWordWrap(True)
        self.what_is_tested_label.setStyleSheet("font-family: monospace;")
        self.content_layout.addWidget(self.what_is_tested_label)

        self.content_layout.addWidget(QLabel("Equivalence (conjunction ≡ original):"))
        self.equivalence_label = QLabel()
        self.equivalence_label.setWordWrap(True)
        self.content_layout.addWidget(self.equivalence_label)

        self.content_layout.addWidget(QLabel("Non-degeneracy (no sub-formula alone ≡ original):"))
        self.nondegeneracy_label = QLabel()
        self.nondegeneracy_label.setWordWrap(True)
        self.content_layout.addWidget(self.nondegeneracy_label)

        retry_row = QVBoxLayout()
        self.retry_button = compact(QPushButton("Retry split with LLM (using this failure as feedback)"))
        self.retry_button.clicked.connect(self._on_retry_clicked)
        retry_row.addWidget(self.retry_button)
        self.content_layout.addLayout(retry_row)

        self.content_layout.addStretch()

    def on_show(self) -> None:
        self._render_what_is_tested()
        self._render(self.state.validation)

    def _selected_requirement(self) -> FretRequirement | None:
        if self.state.fret_import and self.state.selected_requirement_id:
            return self.state.fret_import.requirement(self.state.selected_requirement_id)
        return None

    def _render_what_is_tested(self) -> None:
        """Spells out, in the sub-formulas' own text, exactly what the two checks below compare
        -- without this, a PASS/FAIL per tool gives no way to see what was actually tested."""
        req = self._selected_requirement()
        sub_formulas = self.state.active_sub_formulas()
        if req is None or not sub_formulas:
            self.what_is_tested_label.setText("(select a requirement on page 1 first)")
            return

        lines = [f"Original ({req.reqid}):", f"  pt: {req.pt_formula}", f"  ft: {req.ft_formula}"]

        if len(sub_formulas) == 1 and sub_formulas[0].id == req.reqid:
            lines.append("")
            lines.append("Not split -- nothing to decompose, nothing to validate.")
            self.what_is_tested_label.setText("\n".join(lines))
            return

        lines.append("")
        lines.append("Sub-formulas:")
        for sub in sub_formulas:
            lines.append(f"  {sub.id}:  pt: {sub.pt_formula}")
            lines.append(f"  {' ' * len(sub.id)}  ft: {sub.ft_formula}")

        # Every formula here is already self-parenthesized (FRET's own convention, e.g. "(G a)"),
        # so these are written as-is rather than wrapped again -- unlike the formulas this
        # project builds for feeding into an external tool's parser (where an extra, harmless
        # defensive wrap doesn't matter), this text is for a human to read.
        conjunction_ft = " & ".join(s.ft_formula for s in sub_formulas)
        lines.append("")
        lines.append("Equivalence check:")
        lines.append(f"  {conjunction_ft}")
        lines.append(f"  ≡  {req.ft_formula}  ?")

        lines.append("")
        lines.append("Non-degeneracy checks (each, alone, must NOT already be the whole original):")
        for sub in sub_formulas:
            lines.append(f"  {sub.ft_formula}  ≡  {req.ft_formula}  ?   [{sub.id} -- must be NO]")

        self.what_is_tested_label.setText("\n".join(lines))

    @staticmethod
    def _format_results(results: list[ToolCheckResult]) -> str:
        parts = []
        for r in results:
            verdict = "PASS" if r.passed else "FAIL"
            parts.append(f"{r.tool}: {verdict}" + (f" -- {r.details}" if r.details and not r.passed else ""))
        return "\n".join(parts)

    def _render(self, validation) -> None:
        if validation is None:
            self.equivalence_label.setText("(not validated yet)")
            self.nondegeneracy_label.setText("")
            return

        self.equivalence_label.setStyleSheet(
            "color: #1a7f37;" if all(r.passed for r in validation.equivalence) else "color: #b00020;"
        )
        self.equivalence_label.setText(self._format_results(validation.equivalence))

        if validation.nondegeneracy:
            lines = []
            for sub_id, results in validation.nondegeneracy.items():
                lines.append(f"{sub_id}:\n" + self._format_results(results))
            self.nondegeneracy_label.setStyleSheet(
                "color: #1a7f37;"
                if all(r.passed for results in validation.nondegeneracy.values() for r in results)
                else "color: #b00020;"
            )
            self.nondegeneracy_label.setText("\n".join(lines))
        else:
            self.nondegeneracy_label.setStyleSheet("")
            self.nondegeneracy_label.setText("(single formula, not split -- nothing to check)")

    def _on_validate_clicked(self) -> None:
        req = self._selected_requirement()
        sub_formulas = self.state.active_sub_formulas()
        if req is None or not sub_formulas:
            QMessageBox.information(self, "Nothing to validate", "Import a FRET file and select a requirement on page 1 first.")
            return

        self._render_what_is_tested()
        variables = self.state.fret_import.variables
        try:
            validation = validate_decomposition(req.pt_formula, req.ft_formula, sub_formulas, variables)
        except Exception as exc:  # noqa: BLE001 -- surface any model-checker subprocess/timeout failure
            QMessageBox.critical(self, "Validation failed", f"Couldn't validate the decomposition: {exc}")
            return
        self.state.validation = validation
        self._render(validation)

    def _on_retry_clicked(self) -> None:
        req = self._selected_requirement()
        if req is None or self.state.validation is None:
            QMessageBox.information(self, "Nothing to retry", "Validate a decomposition first.")
            return

        feedback = self._format_results(self.state.validation.equivalence)
        for sub_id, results in self.state.validation.nondegeneracy.items():
            feedback += f"\n{sub_id}: " + self._format_results(results)

        count = len(self.state.sub_formulas) or 2
        api_key = self._settings.value(_API_KEY_SETTING, "")
        try:
            sub_formulas = decompose(req.reqid, req.pt_formula, req.ft_formula, count, api_key=api_key, feedback=feedback)
        except MissingAPIKeyError as exc:
            QMessageBox.information(self, "API key needed", str(exc))
            return
        except Exception as exc:  # noqa: BLE001 -- surface any Anthropic API/network failure
            QMessageBox.critical(self, "Retry failed", f"Couldn't re-decompose the formula: {exc}")
            return

        self.state.split_accepted = True
        self.state.sub_formulas = sub_formulas
        self.state.validation = None
        self._render_what_is_tested()
        self._render(None)
        QMessageBox.information(self, "Retried", "New split generated -- go back to page 1 to review it, or click Validate again.")
