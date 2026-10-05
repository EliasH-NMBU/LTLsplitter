from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .conftest import requires_ogma

from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.monitor_export import MonitorExportPage


def _state_with_import() -> ProjectState:
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(reqid="r1", fulltext="...", pt_formula="(H (request -> grant))", ft_formula="(G (request -> grant))"),
        ],
        variables=[
            Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
            Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
        ],
    )
    return ProjectState(fret_import=fret_import, selected_requirement_id="r1")


def test_generate_without_selection_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(ProjectState())
    qtbot.addWidget(page)

    page._on_generate_clicked()

    assert called == [True]


def test_generate_without_output_dir_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)

    page._on_generate_clicked()

    assert called == [True]


def test_on_show_displays_active_formulas(qtbot):
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "request -> grant" in page.formulas_label.text()


def test_on_show_displays_previously_generated_path(qtbot):
    state = ProjectState(generated_monitor_path="/tmp/some/pkg")
    page = MonitorExportPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "/tmp/some/pkg" in page.status_label.text()


@requires_ogma
def test_generate_success_updates_state(qtbot, tmp_path):
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page._output_dir = Path(tmp_path)

    page._on_generate_clicked()

    assert "generated monitor package" in page.status_label.text().lower()
    assert state.generated_monitor_path == str(tmp_path)
    assert (tmp_path / "copilot" / "src" / "Copilot.hs").is_file()
