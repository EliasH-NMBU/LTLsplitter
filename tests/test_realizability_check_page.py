from PySide6.QtWidgets import QMessageBox

from .conftest import requires_kind2, requires_strix

from ltlsplitter.core.models import FretImport, FretRequirement, RealizabilityResult, Variable, VariableRole, VariableType
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
def test_check_realizable_spec_updates_strix_result(qtbot):
    state = _state_with_import()
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert state.realizability_results["Strix"].realizable is True
    assert "realizable" in page.strix_label.text().lower()


@requires_kind2
def test_check_realizable_spec_updates_kind2_result(qtbot):
    state = _state_with_import()
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert state.realizability_results["Kind2"].realizable is True
    assert "realizable" in page.kind2_label.text().lower()


def test_check_combines_with_other_requirements_in_the_system(qtbot, monkeypatch):
    other = FretRequirement(reqid="r2", fulltext="...", pt_formula="(H (grant -> request))", ft_formula="(G (grant -> request))")
    state = _state_with_import(extra_requirements=[other])
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    captured = {}

    def fake_check_realizability(spec, inputs, outputs):
        captured["ft_formula"] = spec.ltl_formula
        return RealizabilityResult(realizable=True)

    def fake_check_kind2(pt_formulas, variables):
        captured["pt_formulas"] = pt_formulas
        return RealizabilityResult(realizable=True)

    monkeypatch.setattr("ltlsplitter.gui.pages.realizability_check.check_realizability", fake_check_realizability)
    monkeypatch.setattr("ltlsplitter.gui.pages.realizability_check.check_realizability_kind2", fake_check_kind2)

    page._on_check_clicked()

    assert "request -> grant" in captured["ft_formula"]
    assert "grant -> request" in captured["ft_formula"]
    assert captured["pt_formulas"] == ["(H (request -> grant))", "(H (grant -> request))"]


def test_on_show_displays_placeholder_before_checking(qtbot):
    state = _state_with_import()
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "not checked" in page.strix_label.text().lower()
    assert "not checked" in page.kind2_label.text().lower()
