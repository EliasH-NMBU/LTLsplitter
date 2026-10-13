from PySide6.QtWidgets import QMessageBox

from .conftest import requires_kind2, requires_strix

from ltlsplitter.core.models import FretImport, FretRequirement, RealizabilityResult, Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.realizability_check import RealizabilityCheckPage


def _state_with_import(requirements=None) -> ProjectState:
    fret_import = FretImport(
        project="demo",
        requirements=requirements if requirements is not None else [
            FretRequirement(
                reqid="r1", fulltext="...",
                pt_formula="(H (request -> grant))", ft_formula="(G (request -> grant))",
            ),
        ],
        variables=[
            Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
            Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
        ],
    )
    return ProjectState(fret_import=fret_import)


def test_check_without_import_shows_message(qtbot, monkeypatch):
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
    state = ProjectState(fret_import=fret_import)
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert called == [True]


def test_check_requires_no_requirement_selection(qtbot, monkeypatch):
    """The whole point of the redesign: no state.selected_requirement_id needed at all --
    the check covers every leaf requirement in the imported file directly."""
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.realizability_check.check_realizability_typed",
        lambda formula, variables, requirement_id: RealizabilityResult(realizable=True),
    )
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.realizability_check.check_realizability_kind2",
        lambda assumption_pt_formulas, guarantee_pt_formulas, variables: RealizabilityResult(realizable=True),
    )
    state = _state_with_import()
    assert state.selected_requirement_id is None
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_clicked()

    assert state.realizability_results["Strix"].realizable is True


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


def test_check_combines_every_leaf_requirement_exactly_once(qtbot, monkeypatch):
    """A split parent (r1, now superseded by r1.1/r1.2) must not be double-counted against its
    own saved children -- the historical bug this redesign specifically fixes."""
    requirements = [
        FretRequirement(reqid="r1", fulltext="...", pt_formula="(H (request -> grant))", ft_formula="(G (request -> grant))"),
        FretRequirement(reqid="r1.1", fulltext="...", pt_formula="(H r1a)", ft_formula="(G r1a)", parent_reqid="r1"),
        FretRequirement(reqid="r1.2", fulltext="...", pt_formula="(H r1b)", ft_formula="(G r1b)", parent_reqid="r1"),
        FretRequirement(reqid="r2", fulltext="...", pt_formula="(H (grant -> request))", ft_formula="(G (grant -> request))"),
    ]
    state = _state_with_import(requirements=requirements)
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    captured = {}

    def fake_check_realizability_typed(formula, variables, requirement_id):
        captured["ft_formula"] = formula
        return RealizabilityResult(realizable=True)

    def fake_check_kind2(assumption_pt_formulas, guarantee_pt_formulas, variables):
        captured["pt_formulas"] = guarantee_pt_formulas
        return RealizabilityResult(realizable=True)

    monkeypatch.setattr(
        "ltlsplitter.gui.pages.realizability_check.check_realizability_typed", fake_check_realizability_typed
    )
    monkeypatch.setattr("ltlsplitter.gui.pages.realizability_check.check_realizability_kind2", fake_check_kind2)

    page._on_check_clicked()

    # r1's own formula must NOT appear -- it's superseded by r1.1/r1.2.
    assert "request -> grant" not in captured["ft_formula"]
    assert "r1a" in captured["ft_formula"] and "r1b" in captured["ft_formula"]
    assert "grant -> request" in captured["ft_formula"]
    assert captured["pt_formulas"] == ["(H r1a)", "(H r1b)", "(H (grant -> request))"]


def test_check_treats_assumption_requirements_as_assumptions_not_guarantees(qtbot, monkeypatch):
    """A requirement marked is_assumption must become a Strix assumption (A -> G shape) and a
    Kind2 `assume`, not get flat-ANDed in as a guarantee -- the fix for the "unrealizable"
    verdicts that showed up when every requirement, including environment-assumption ones like
    "classifier is in {0,1,2}", was guaranteed uniformly."""
    requirements = [
        FretRequirement(
            reqid="classifier_assumption", fulltext="...", pt_formula="(H (classifier = 1))",
            ft_formula="(G (classifier = 1))", is_assumption=True,
        ),
        FretRequirement(
            reqid="r1", fulltext="...", pt_formula="(H (classifier = 1 -> grant))",
            ft_formula="(G (classifier = 1 -> grant))",
        ),
    ]
    state = _state_with_import(requirements=requirements)
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    captured = {}

    def fake_check_realizability_typed(formula, variables, requirement_id):
        captured["ft_formula"] = formula
        return RealizabilityResult(realizable=True)

    def fake_check_kind2(assumption_pt_formulas, guarantee_pt_formulas, variables):
        captured["assumption_pt_formulas"] = assumption_pt_formulas
        captured["guarantee_pt_formulas"] = guarantee_pt_formulas
        return RealizabilityResult(realizable=True)

    monkeypatch.setattr(
        "ltlsplitter.gui.pages.realizability_check.check_realizability_typed", fake_check_realizability_typed
    )
    monkeypatch.setattr("ltlsplitter.gui.pages.realizability_check.check_realizability_kind2", fake_check_kind2)

    page._on_check_clicked()

    assert captured["ft_formula"] == "(((G (classifier = 1)))) -> (((G (classifier = 1 -> grant))))"
    assert captured["assumption_pt_formulas"] == ["(H (classifier = 1))"]
    assert captured["guarantee_pt_formulas"] == ["(H (classifier = 1 -> grant))"]


def test_on_show_displays_placeholder_before_checking(qtbot):
    state = _state_with_import()
    page = RealizabilityCheckPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "not checked" in page.strix_label.text().lower()
    assert "not checked" in page.kind2_label.text().lower()
