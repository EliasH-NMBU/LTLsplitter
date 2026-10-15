from pathlib import Path

from PySide6.QtWidgets import QMessageBox

from .conftest import requires_ogma

from ltlsplitter.core.models import FretImport, FretRequirement, SubFormula, Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.monitor_export import MonitorExportPage


def _state_with_import(fret_import_path: str = "/some/original.json") -> ProjectState:
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
    return ProjectState(fret_import=fret_import, fret_import_path=fret_import_path, selected_requirement_id="r1")


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


def test_on_show_displays_the_source_file_path(qtbot):
    state = _state_with_import(fret_import_path="/some/original.json")
    page = MonitorExportPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "/some/original.json" in page.source_file_label.text()
    assert "r1" in page.source_file_label.text()


def test_on_show_reflects_the_file_a_split_was_saved_to(qtbot):
    """The whole point of showing a source file at all: after a split is saved (import_split.py's
    _save_split repoints state.fret_import_path at the new copy), this page must show *that*
    file, not the one originally imported -- it's genuinely a different file on disk."""
    state = _state_with_import(fret_import_path="/some/original.json")
    # Simulate what _save_split does on an accepted split: a new copy becomes the active file,
    # and its sub-formulas become what's exported.
    state.fret_import_path = "/some/ltlsplitter_exports/r1_split.json"
    state.split_accepted = True
    state.sub_formulas = [
        SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
        SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)"),
    ]
    page = MonitorExportPage(state)
    qtbot.addWidget(page)

    page.on_show()

    text = page.source_file_label.text()
    assert "/some/ltlsplitter_exports/r1_split.json" in text
    assert "/some/original.json" not in text
    assert "r1.1" in text and "r1.2" in text


def test_on_show_without_an_import_shows_placeholder(qtbot):
    page = MonitorExportPage(ProjectState())
    qtbot.addWidget(page)

    page.on_show()

    assert "no file imported" in page.source_file_label.text().lower()


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
