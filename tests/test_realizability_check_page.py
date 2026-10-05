from PySide6.QtWidgets import QMessageBox

from .conftest import requires_strix

from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.realizability_check import RealizabilityCheckPage


def _state_with_import(extra_requirements=()) -> ProjectState:
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(
                reqid="r1", fulltext="...",
                pt_formula="(H (request -> grant))", ft_formula="(G (request -> grant))",
            ),
            *extra_requirements,
        ],
        variables=[
            Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
            Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
        ],
    )
    return ProjectState(fret_import=fret_import, selected_requirement_id="r1")


def test_check_without_selection_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = RealizabilityCheckPage(ProjectState())
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert called == [True]


def test_check_without_output_variables_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    fret_import = FretImport(
        project="demo",
        requirements=[FretRequirement(reqid="r1", fulltext="...", pt_formula="(H a)", ft_formula="(G a)")],
        variables=[Variable(name="a", type=VariableType.BOOL, role=VariableRole.INPUT)],
    )
    state = ProjectState(fret_import=fret_import, selected_requirement_id="r1")
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert called == [True]


@requires_strix
def test_check_realizable_spec_updates_state(qtbot):
    state = _state_with_import()
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert state.realizability_result is not None
    assert state.realizability_result.realizable is True
    assert "realizable" in page.result_label.text().lower()


def test_check_combines_with_other_requirements_in_the_system(qtbot, monkeypatch):
    other = FretRequirement(reqid="r2", fulltext="...", pt_formula="(H (grant -> request))", ft_formula="(G (grant -> request))")
    state = _state_with_import(extra_requirements=[other])
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    captured = {}

    def fake_check_realizability(spec, inputs, outputs):
        captured["formula"] = spec.ltl_formula
        from ltlsplitter.core.models import RealizabilityResult
        return RealizabilityResult(realizable=True)

    monkeypatch.setattr("ltlsplitter.gui.pages.realizability_check.check_realizability", fake_check_realizability)

    page._on_check_clicked()

    assert "request -> grant" in captured["formula"]
    assert "grant -> request" in captured["formula"]
