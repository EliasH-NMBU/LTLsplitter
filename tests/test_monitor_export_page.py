from pathlib import Path

from PySide6.QtWidgets import QInputDialog, QMessageBox

from .conftest import requires_ogma

from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.monitor_export import MonitorExportPage, _UNGROUPED, _sanitize_dirname


def _req(reqid, pt="(H a)", ft="(G a)", variables=None, parent_reqid="") -> FretRequirement:
    return FretRequirement(
        reqid=reqid, fulltext="...", pt_formula=pt, ft_formula=ft,
        variable_names=variables or [], parent_reqid=parent_reqid,
    )


def _state_with_import(fret_import_path: str = "/some/original.json") -> ProjectState:
    fret_import = FretImport(
        project="demo",
        requirements=[_req("r1", "(H (request -> grant))", "(G (request -> grant))", ["request", "grant"])],
        variables=[
            Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
            Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
        ],
    )
    return ProjectState(fret_import=fret_import, fret_import_path=fret_import_path)


def _state_with_three_requirements() -> ProjectState:
    """r1/r2 share variable "a" (should auto-group together); r3 is unrelated."""
    fret_import = FretImport(
        project="demo",
        requirements=[
            _req("r1", variables=["a", "b"]),
            _req("r2", variables=["a", "c"]),
            _req("r3", variables=["z"]),
        ],
        variables=[Variable(name=n, type=VariableType.BOOL) for n in ("a", "b", "c", "z")],
    )
    return ProjectState(fret_import=fret_import, fret_import_path="/some/file.json")


def _group_member_texts(page: MonitorExportPage, group_name: str) -> list[str]:
    for i in range(page.group_tree.topLevelItemCount()):
        item = page.group_tree.topLevelItem(i)
        if item.text(0) == group_name:
            return [item.child(j).text(0) for j in range(item.childCount())]
    raise AssertionError(f"no top-level group named {group_name!r}")


def test_generate_without_fret_import_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(ProjectState())
    qtbot.addWidget(page)

    page._on_generate_clicked()

    assert called == [True]


def test_generate_without_a_group_shows_message(qtbot, monkeypatch):
    """Only "Ungrouped" exists until the user creates a real group -- nothing is exportable yet."""
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    page._on_generate_clicked()

    assert called == [True]


def test_generate_with_empty_group_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    page.group_tree.addTopLevelItem(page._group_header_item("Empty Group", editable=True))
    page._refresh_export_group_selector()
    page.export_group_combo.setCurrentText("Empty Group")

    page._on_generate_clicked()

    assert called == [True]


def test_generate_without_output_dir_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    page._on_auto_suggest_clicked()

    page._on_generate_clicked()

    assert called == [True]


def test_on_show_displays_the_source_file_path(qtbot):
    page = MonitorExportPage(_state_with_import(fret_import_path="/some/original.json"))
    qtbot.addWidget(page)

    page.on_show()

    assert "/some/original.json" in page.source_file_label.text()
    assert "1 requirement(s)" in page.source_file_label.text()


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


# -- grouping -----------------------------------------------------------------------------


def test_on_show_builds_tree_with_everything_ungrouped_for_a_fresh_import(qtbot):
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)

    page.on_show()

    assert page.group_tree.topLevelItemCount() == 1
    assert page.group_tree.topLevelItem(0).text(0) == _UNGROUPED
    assert set(_group_member_texts(page, _UNGROUPED)) == {"r1", "r2", "r3"}


def test_on_show_rebuilds_the_tree_when_leaf_requirements_change(qtbot):
    """A split saved as real nested requirements (import_split.py's _save_split) changes the
    leaf set -- the tree must drop the now-superseded parent and pick up its children, the same
    "entire current system" rule the realizability check already follows."""
    fret_import = FretImport(
        project="demo",
        requirements=[_req("r1", variables=["a"])],
        variables=[Variable(name="a", type=VariableType.BOOL)],
    )
    state = ProjectState(fret_import=fret_import, fret_import_path="/some/file.json")
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    assert set(_group_member_texts(page, _UNGROUPED)) == {"r1"}

    fret_import.requirements = [
        _req("r1", variables=["a"]),
        _req("r1.1", variables=["a"], parent_reqid="r1"),
        _req("r1.2", variables=["a"], parent_reqid="r1"),
    ]
    page.on_show()

    assert set(_group_member_texts(page, _UNGROUPED)) == {"r1.1", "r1.2"}


def test_on_show_preserves_manual_grouping_when_leaf_set_is_unchanged(qtbot, monkeypatch):
    """Revisiting this page (e.g. after checking page 3 then coming back) must not silently
    discard a grouping the user already set up by hand."""
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("My Group", True))
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    page._on_add_group_clicked()

    page.on_show()

    assert page.group_tree.topLevelItemCount() == 2
    assert any(page.group_tree.topLevelItem(i).text(0) == "My Group" for i in range(page.group_tree.topLevelItemCount()))


def test_auto_suggest_clusters_requirements_sharing_a_variable(qtbot):
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()

    page._on_auto_suggest_clicked()

    # r1/r2 (share "a") end up in one group; r3 (unrelated) in its own; Ungrouped stays empty.
    assert page.group_tree.topLevelItemCount() == 3
    assert _group_member_texts(page, _UNGROUPED) == []
    groups = {page.group_tree.topLevelItem(i).text(0): _group_member_texts(page, page.group_tree.topLevelItem(i).text(0))
              for i in range(1, page.group_tree.topLevelItemCount())}
    assert {"r1", "r2"} in [set(v) for v in groups.values()]
    assert {"r3"} in [set(v) for v in groups.values()]


def test_add_group_creates_a_new_top_level_item(qtbot, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("New Group", True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    page._on_add_group_clicked()

    assert page.group_tree.topLevelItemCount() == 2
    assert page.export_group_combo.findText("New Group") != -1


def test_add_group_cancelled_adds_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("", False))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    page._on_add_group_clicked()

    assert page.group_tree.topLevelItemCount() == 1


def test_remove_group_moves_children_back_to_ungrouped(qtbot):
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    page._on_auto_suggest_clicked()
    ab_group_item = next(
        page.group_tree.topLevelItem(i) for i in range(page.group_tree.topLevelItemCount())
        if set(_group_member_texts(page, page.group_tree.topLevelItem(i).text(0)) if page.group_tree.topLevelItem(i).text(0) != _UNGROUPED else []) == {"r1", "r2"}
    )
    page.group_tree.setCurrentItem(ab_group_item)

    page._on_remove_group_clicked()

    assert set(_group_member_texts(page, _UNGROUPED)) == {"r1", "r2"}
    assert page.group_tree.topLevelItemCount() == 2  # Ungrouped + the r3-only group


def test_remove_ungrouped_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    page.group_tree.setCurrentItem(page.group_tree.topLevelItem(0))

    page._on_remove_group_clicked()

    assert called == [True]
    assert page.group_tree.topLevelItemCount() == 1


def test_export_group_selector_excludes_ungrouped(qtbot):
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    page._on_auto_suggest_clicked()

    names = [page.export_group_combo.itemText(i) for i in range(page.export_group_combo.count())]

    assert _UNGROUPED not in names


def test_renaming_a_group_updates_the_export_selector(qtbot):
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    group_item = page._group_header_item("Original Name", editable=True)
    page.group_tree.addTopLevelItem(group_item)
    page._refresh_export_group_selector()
    assert page.export_group_combo.findText("Original Name") != -1

    group_item.setText(0, "Renamed")
    page._on_group_tree_item_changed(group_item, 0)

    assert page.export_group_combo.findText("Renamed") != -1
    assert page.export_group_combo.findText("Original Name") == -1


# -- export ------------------------------------------------------------------------------


def test_sanitize_dirname_produces_a_filesystem_safe_slug():
    assert _sanitize_dirname("Group 1: classifier, state") == "Group_1__classifier__state"
    assert _sanitize_dirname("  leading and trailing  ") == "leading_and_trailing"


def test_generate_uses_only_the_selected_groups_requirements(qtbot, monkeypatch, tmp_path):
    captured = {}

    def fake_generate(specs, output_dir, variables):
        captured["specs"] = specs
        captured["output_dir"] = output_dir
        return output_dir

    monkeypatch.setattr("ltlsplitter.gui.pages.monitor_export.generate_ros2_monitor", fake_generate)
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    page._on_auto_suggest_clicked()
    page.export_group_combo.setCurrentText(next(
        page.group_tree.topLevelItem(i).text(0) for i in range(page.group_tree.topLevelItemCount())
        if set(_group_member_texts(page, page.group_tree.topLevelItem(i).text(0)) if page.group_tree.topLevelItem(i).text(0) != _UNGROUPED else []) == {"r1", "r2"}
    ))
    page._output_dir = tmp_path

    page._on_generate_clicked()

    assert {s.requirement_id for s in captured["specs"]} == {"r1", "r2"}
    assert captured["output_dir"] == tmp_path / _sanitize_dirname(page.export_group_combo.currentText())


@requires_ogma
def test_generate_success_updates_state(qtbot, tmp_path):
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page._on_auto_suggest_clicked()
    page._output_dir = Path(tmp_path)
    group_name = page.export_group_combo.itemText(0)
    page.export_group_combo.setCurrentText(group_name)

    page._on_generate_clicked()

    assert "generated monitor package" in page.status_label.text().lower()
    expected_dir = Path(tmp_path) / _sanitize_dirname(group_name)
    assert state.generated_monitor_path == str(expected_dir)
    assert (expected_dir / "copilot" / "src" / "Copilot.hs").is_file()
