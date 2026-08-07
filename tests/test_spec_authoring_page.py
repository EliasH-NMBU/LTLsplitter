from ltlsplitter.core.models import Variable, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.spec_authoring import SpecAuthoringPage


def test_on_show_populates_requirements_and_variables(qtbot):
    state = ProjectState(
        sub_requirements=["a", "b"],
        variables=[Variable(name="x", type=VariableType.BOOL, ros_node="/n")],
    )
    page = SpecAuthoringPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert page.requirement_list.count() == 2
    assert page.variables_label.text() == "x"


def test_editing_formula_saves_to_spec(qtbot):
    state = ProjectState(sub_requirements=["a"])
    page = SpecAuthoringPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page.formula_edit.setPlainText("G (x -> F y)")

    assert state.spec_for("r1.1").ltl_formula == "G (x -> F y)"


def test_validate_flags_undeclared_reference(qtbot):
    state = ProjectState(
        sub_requirements=["a"],
        variables=[Variable(name="x", type=VariableType.BOOL, ros_node="/n")],
    )
    page = SpecAuthoringPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.formula_edit.setPlainText("G (x -> F y)")

    page._on_validate_clicked()

    assert "y" in page.validation_label.text()


def test_switching_requirement_preserves_each_formula(qtbot):
    state = ProjectState(sub_requirements=["a", "b"])
    page = SpecAuthoringPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page.requirement_list.setCurrentRow(0)
    page.formula_edit.setPlainText("G a")
    page.requirement_list.setCurrentRow(1)
    page.formula_edit.setPlainText("G b")

    assert state.spec_for("r1.1").ltl_formula == "G a"
    assert state.spec_for("r1.2").ltl_formula == "G b"
