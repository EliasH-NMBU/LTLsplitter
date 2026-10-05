from PySide6.QtWidgets import QMessageBox

from ltlsplitter.core.models import (
    DecompositionValidation,
    FretImport,
    FretRequirement,
    SubFormula,
    ToolCheckResult,
    Variable,
    VariableType,
)
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.decomposition_validation import DecompositionValidationPage


def _state_with_import() -> ProjectState:
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(reqid="r1", fulltext="...", pt_formula="(H (a -> b))", ft_formula="(G (a -> b))"),
        ],
        variables=[Variable(name="a", type=VariableType.BOOL), Variable(name="b", type=VariableType.BOOL)],
    )
    return ProjectState(fret_import=fret_import, selected_requirement_id="r1")


def test_validate_without_selection_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = DecompositionValidationPage(ProjectState())
    qtbot.addWidget(page)

    page._on_validate_clicked()

    assert called == [True]


def test_validate_runs_check_and_renders_results(qtbot, monkeypatch):
    validation = DecompositionValidation(
        equivalence=[ToolCheckResult(tool="nuXmv", passed=True)],
        nondegeneracy={},
    )
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.decomposition_validation.validate_decomposition",
        lambda original_pt, original_ft, subs, variables: validation,
    )
    state = _state_with_import()
    page = DecompositionValidationPage(state)
    qtbot.addWidget(page)

    page._on_validate_clicked()

    assert state.validation is validation
    assert "nuxmv: pass" in page.equivalence_label.text().lower()


def test_on_show_with_no_prior_validation_shows_placeholder(qtbot):
    page = DecompositionValidationPage(ProjectState())
    qtbot.addWidget(page)

    page.on_show()

    assert "not validated" in page.equivalence_label.text().lower()


def test_retry_without_prior_validation_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = DecompositionValidationPage(_state_with_import())
    qtbot.addWidget(page)

    page._on_retry_clicked()

    assert called == [True]


def test_retry_calls_decompose_and_resets_validation(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    new_subs = [SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)")]
    captured = {}

    def fake_decompose(parent_id, pt, ft, count, api_key=None, feedback=None):
        captured["feedback"] = feedback
        return new_subs

    monkeypatch.setattr("ltlsplitter.gui.pages.decomposition_validation.decompose", fake_decompose)

    state = _state_with_import()
    state.validation = DecompositionValidation(equivalence=[ToolCheckResult(tool="nuXmv", passed=False, details="boom")])
    page = DecompositionValidationPage(state)
    qtbot.addWidget(page)

    page._on_retry_clicked()

    assert state.sub_formulas == new_subs
    assert state.split_accepted is True
    assert state.validation is None
    assert "boom" in captured["feedback"]
