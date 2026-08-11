from pathlib import Path

from .conftest import requires_ogma

from ltlsplitter.core.models import Variable, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.monitor_generation import MonitorGenerationPage


def test_on_show_lists_only_requirements_with_formulas(qtbot):
    state = ProjectState(sub_requirements=["a", "b"])
    state.spec_for("r1.1").ltl_formula = "G x"
    page = MonitorGenerationPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert page.requirement_list.count() == 1


def test_generate_without_selection_shows_message(qtbot, monkeypatch):
    shown = {}
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.monitor_generation.QMessageBox.information",
        lambda *a, **kw: shown.setdefault("called", True),
    )
    state = ProjectState()
    page = MonitorGenerationPage(state)
    qtbot.addWidget(page)

    page._on_generate_clicked()

    assert shown.get("called")


def test_generate_without_output_dir_shows_message(qtbot, monkeypatch, tmp_path):
    shown = {}
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.monitor_generation.QMessageBox.information",
        lambda *a, **kw: shown.setdefault("called", True),
    )
    state = ProjectState(sub_requirements=["a"])
    state.spec_for("r1.1").ltl_formula = "G x"
    page = MonitorGenerationPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.requirement_list.setCurrentRow(0)

    page._on_generate_clicked()

    assert shown.get("called")


@requires_ogma
def test_generate_success_updates_state(qtbot, tmp_path):
    state = ProjectState(
        sub_requirements=["a"],
        variables=[Variable(name="x", type=VariableType.BOOL, ros_node="/n")],
    )
    state.spec_for("r1.1").ltl_formula = "G x"
    page = MonitorGenerationPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.requirement_list.setCurrentRow(0)
    page._output_dir = Path(tmp_path)

    page._on_generate_clicked()

    assert "generated monitor package" in page.status_label.text().lower()
    assert state.generated_monitor_path == str(tmp_path)
    assert (tmp_path / "copilot" / "src" / "Copilot.hs").is_file()


@requires_ogma
def test_generate_nested_temporal_operator_fails_clearly(qtbot, tmp_path):
    state = ProjectState(
        sub_requirements=["a"],
        variables=[
            Variable(name="request", type=VariableType.BOOL, ros_node="/n"),
            Variable(name="grant", type=VariableType.BOOL, ros_node="/n"),
        ],
    )
    state.spec_for("r1.1").ltl_formula = "G (request -> F grant)"
    page = MonitorGenerationPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.requirement_list.setCurrentRow(0)
    page._output_dir = Path(tmp_path)

    page._on_generate_clicked()

    assert "generation failed" in page.status_label.text().lower()
    assert "nested" in page.status_label.text().lower() or "temporal operator" in page.status_label.text().lower()


def test_on_show_displays_previously_generated_path(qtbot):
    state = ProjectState(generated_monitor_path="/tmp/some/pkg")
    page = MonitorGenerationPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "/tmp/some/pkg" in page.status_label.text()
