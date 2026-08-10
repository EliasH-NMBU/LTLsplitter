from .conftest import requires_nuxmv, requires_strix

from ltlsplitter.core.models import Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.consistency_check import ConsistencyCheckPage


def test_on_show_lists_only_requirements_with_formulas(qtbot):
    state = ProjectState(sub_requirements=["a", "b"])
    state.spec_for("r1.1").ltl_formula = "G x"
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert page.requirement_list.count() == 1


def test_check_consistency_without_specs_shows_message(qtbot, monkeypatch):
    shown = {}
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.consistency_check.QMessageBox.information",
        lambda *a, **kw: shown.setdefault("called", True),
    )
    state = ProjectState()
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)

    page._on_check_consistency_clicked()

    assert shown.get("called")


@requires_nuxmv
def test_check_consistency_flags_conflicting_requirements(qtbot):
    state = ProjectState(
        sub_requirements=["a", "b"],
        variables=[Variable(name="x", type=VariableType.BOOL, ros_node="/n")],
    )
    state.spec_for("r1.1").ltl_formula = "G x"
    state.spec_for("r1.2").ltl_formula = "G !x"
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page._on_check_consistency_clicked()

    assert "inconsistent" in page.consistency_label.text().lower()
    assert "r1.1" in page.consistency_label.text() and "r1.2" in page.consistency_label.text()


@requires_nuxmv
def test_check_consistency_passes_for_compatible_requirements(qtbot):
    state = ProjectState(
        sub_requirements=["a"],
        variables=[Variable(name="x", type=VariableType.BOOL, ros_node="/n")],
    )
    state.spec_for("r1.1").ltl_formula = "G x"
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page._on_check_consistency_clicked()

    assert "consistent" in page.consistency_label.text().lower()
    assert "inconsistent" not in page.consistency_label.text().lower()


def test_check_realizability_requires_output_variable(qtbot, monkeypatch):
    shown = {}
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.consistency_check.QMessageBox.information",
        lambda *a, **kw: shown.setdefault("called", True),
    )
    state = ProjectState(
        sub_requirements=["a"],
        variables=[Variable(name="x", type=VariableType.BOOL, ros_node="/n", role=VariableRole.INPUT)],
    )
    state.spec_for("r1.1").ltl_formula = "G x"
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.requirement_list.setCurrentRow(0)

    page._on_check_realizability_clicked()

    assert shown.get("called")


@requires_strix
def test_check_realizability_passes_for_realizable_spec(qtbot):
    state = ProjectState(
        sub_requirements=["a"],
        variables=[
            Variable(name="request", type=VariableType.BOOL, ros_node="/n", role=VariableRole.INPUT),
            Variable(name="grant", type=VariableType.BOOL, ros_node="/n", role=VariableRole.OUTPUT),
        ],
    )
    state.spec_for("r1.1").ltl_formula = "G (request -> F grant)"
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.requirement_list.setCurrentRow(0)

    page._on_check_realizability_clicked()

    assert page.realizability_label.text() == "Realizable: a satisfying strategy exists."


@requires_strix
def test_check_realizability_flags_unrealizable_spec(qtbot):
    state = ProjectState(
        sub_requirements=["a"],
        variables=[
            Variable(name="request", type=VariableType.BOOL, ros_node="/n", role=VariableRole.INPUT),
            Variable(name="grant", type=VariableType.BOOL, ros_node="/n", role=VariableRole.OUTPUT),
        ],
    )
    state.spec_for("r1.1").ltl_formula = "G (grant <-> (X request))"
    page = ConsistencyCheckPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.requirement_list.setCurrentRow(0)

    page._on_check_realizability_clicked()

    assert "not realizable" in page.realizability_label.text().lower()
