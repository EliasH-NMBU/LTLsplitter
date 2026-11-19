from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox, QToolTip

from .conftest import requires_ogma

from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.monitor_export import (
    MonitorExportPage,
    _UNASSIGNED_REQUIREMENTS,
    _UNASSIGNED_VARIABLES,
    _VariableColumnList,
    _sanitize_dirname,
)


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


def _state_for_auto_sort() -> ProjectState:
    """r1 only uses "a" (unambiguous), r2 only uses "b" (unambiguous), r3 uses both (ambiguous
    once a/b are in different groups -- the exact example from the request), r4 uses "z", which
    is never placed in any group."""
    fret_import = FretImport(
        project="demo",
        requirements=[
            _req("r1", variables=["a"]),
            _req("r2", variables=["b"]),
            _req("r3", variables=["a", "b"]),
            _req("r4", variables=["z"]),
        ],
        variables=[Variable(name=n, type=VariableType.BOOL) for n in ("a", "b", "z")],
    )
    return ProjectState(fret_import=fret_import, fret_import_path="/some/file.json")


def _column(page: MonitorExportPage, name: str):
    for column in page._variable_columns:
        if column.name == name:
            return column
    raise AssertionError(f"no variable column named {name!r}")


def _variable_member_texts(page: MonitorExportPage, group_name: str) -> list[str]:
    column = _column(page, group_name)
    return [column.list_widget.item(i).text() for i in range(column.list_widget.count())]


def _requirement_member_texts(page: MonitorExportPage, group_name: str) -> list[str]:
    for i in range(page.requirement_tree.topLevelItemCount()):
        item = page.requirement_tree.topLevelItem(i)
        if item.text(0) == group_name:
            return [item.child(j).text(0) for j in range(item.childCount())]
    raise AssertionError(f"no top-level requirement group named {group_name!r}")


def _add_group(page: MonitorExportPage, monkeypatch, name: str) -> None:
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: (name, True))
    page._on_add_group_clicked()


def _move_variable_to_group(page: MonitorExportPage, var_name: str, group_name: str) -> None:
    """Simulates what dragging a variable into a column produces -- real Qt drag-and-drop isn't
    simulated here (_VariableColumnList.dropEvent itself is covered separately, directly)."""
    for column in page._variable_columns:
        items = column.list_widget.findItems(var_name, Qt.MatchFlag.MatchExactly)
        if items:
            column.list_widget.takeItem(column.list_widget.row(items[0]))
            break
    else:
        raise AssertionError(f"variable {var_name!r} not found in any column")
    _column(page, group_name).list_widget.addItem(var_name)


def test_generate_without_fret_import_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(ProjectState())
    qtbot.addWidget(page)

    page._on_generate_clicked()

    assert called == [True]


def test_generate_without_a_group_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    page._on_generate_clicked()

    assert called == [True]


def test_generate_with_empty_group_shows_message(qtbot, monkeypatch):
    called = []
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Empty Group")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page.export_group_combo.setCurrentText("Empty Group")

    page._on_generate_clicked()

    assert called == [True]


def test_generate_without_output_dir_shows_message(qtbot, monkeypatch):
    called = []
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group 1")
    _move_variable_to_group(page, "request", "Group 1")
    _move_variable_to_group(page, "grant", "Group 1")
    page._on_auto_sort_clicked()
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))

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


# -- variable topics -----------------------------------------------------------------------


def _topic_rows(page: MonitorExportPage) -> dict[str, str]:
    return {
        page.topics_tree.topLevelItem(i).text(0): page.topics_tree.topLevelItem(i).text(1)
        for i in range(page.topics_tree.topLevelItemCount())
    }


def test_on_show_seeds_default_topics_for_input_and_output_variables(qtbot):
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)

    page.on_show()

    assert _topic_rows(page) == {"request": "/request", "grant": "/grant"}


def test_internal_variables_are_excluded_from_the_topics_table(qtbot):
    fret_import = FretImport(
        project="demo",
        requirements=[_req("r1", variables=["a", "b"])],
        variables=[
            Variable(name="a", type=VariableType.BOOL, role=VariableRole.INPUT),
            Variable(name="b", type=VariableType.BOOL, role=VariableRole.INTERNAL),
        ],
    )
    page = MonitorExportPage(ProjectState(fret_import=fret_import, fret_import_path="/f.json"))
    qtbot.addWidget(page)

    page.on_show()

    assert _topic_rows(page) == {"a": "/a"}


def test_editing_a_topic_cell_updates_the_underlying_variable(qtbot):
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    item = page.topics_tree.topLevelItem(0)

    item.setText(1, "/sensors/request")

    assert state.fret_import.variables[0].topic == "/sensors/request"


def test_clearing_a_topic_cell_falls_back_to_the_default(qtbot):
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    item = page.topics_tree.topLevelItem(0)

    item.setText(1, "   ")

    assert state.fret_import.variables[0].topic == "/request"
    assert item.text(1) == "/request"


def test_revisiting_the_page_preserves_a_topic_override(qtbot):
    """Same rule as the grouping widgets below: an unchanged variable set must not silently
    discard an override the user already typed in just because the page was shown again."""
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.topics_tree.topLevelItem(0).setText(1, "/custom/topic")

    page.on_show()

    assert _topic_rows(page)["request"] == "/custom/topic"


def test_generate_passes_the_overridden_topic_through_to_ogma(qtbot, monkeypatch, tmp_path):
    captured = {}

    def fake_generate(specs, output_dir, variables):
        captured["variables"] = variables
        return output_dir

    monkeypatch.setattr("ltlsplitter.gui.pages.monitor_export.generate_ros2_monitor", fake_generate)
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    page.topics_tree.topLevelItem(0).setText(1, "/custom/topic")
    _add_group(page, monkeypatch, "Group 1")
    _move_variable_to_group(page, "request", "Group 1")
    _move_variable_to_group(page, "grant", "Group 1")
    page._on_auto_sort_clicked()
    page._output_dir = tmp_path
    page.export_group_combo.setCurrentText("Group 1")

    page._on_generate_clicked()

    by_name = {v.name: v.topic for v in captured["variables"]}
    assert by_name["request"] == "/custom/topic"


def test_on_show_displays_previously_generated_path(qtbot):
    state = ProjectState(generated_monitor_path="/tmp/some/pkg")
    page = MonitorExportPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert "/tmp/some/pkg" in page.status_label.text()


# -- variable grouping (one column per group) ------------------------------------------------


def test_on_show_builds_everything_unassigned_for_a_fresh_import(qtbot):
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)

    page.on_show()

    assert len(page._variable_columns) == 1
    assert page._variable_columns[0].name == _UNASSIGNED_VARIABLES
    assert set(_variable_member_texts(page, _UNASSIGNED_VARIABLES)) == {"a", "b", "c", "z"}

    assert page.requirement_tree.topLevelItemCount() == 1
    assert page.requirement_tree.topLevelItem(0).text(0) == _UNASSIGNED_REQUIREMENTS
    assert set(_requirement_member_texts(page, _UNASSIGNED_REQUIREMENTS)) == {"r1", "r2", "r3"}


def test_on_show_rebuilds_the_requirement_tree_when_leaf_requirements_change(qtbot):
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
    assert set(_requirement_member_texts(page, _UNASSIGNED_REQUIREMENTS)) == {"r1"}

    fret_import.requirements = [
        _req("r1", variables=["a"]),
        _req("r1.1", variables=["a"], parent_reqid="r1"),
        _req("r1.2", variables=["a"], parent_reqid="r1"),
    ]
    page.on_show()

    assert set(_requirement_member_texts(page, _UNASSIGNED_REQUIREMENTS)) == {"r1.1", "r1.2"}


def test_on_show_preserves_manual_variable_grouping_when_set_is_unchanged(qtbot, monkeypatch):
    """Revisiting this page (e.g. after checking page 3 then coming back) must not silently
    discard a grouping the user already set up by hand."""
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "My Group")

    page.on_show()

    assert len(page._variable_columns) == 2
    assert any(column.name == "My Group" for column in page._variable_columns)


def test_add_group_creates_a_matching_empty_column_and_requirement_group(qtbot, monkeypatch):
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    _add_group(page, monkeypatch, "New Group")

    assert len(page._variable_columns) == 2
    assert page.requirement_tree.topLevelItemCount() == 2
    assert _variable_member_texts(page, "New Group") == []
    assert _requirement_member_texts(page, "New Group") == []
    assert page.export_group_combo.findText("New Group") != -1
    # The new column sits to the right of the stretch-less layout, right before the trailing
    # stretch item that keeps columns left-aligned.
    assert page._variable_columns_layout.count() == 3  # pool + new group + trailing stretch


def test_add_group_cancelled_adds_nothing(qtbot, monkeypatch):
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("", False))
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    page._on_add_group_clicked()

    assert len(page._variable_columns) == 1
    assert page.requirement_tree.topLevelItemCount() == 1


def test_add_group_rejects_a_duplicate_name(qtbot, monkeypatch):
    called = []
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group 1")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))

    _add_group(page, monkeypatch, "Group 1")

    assert called == [True]
    assert len(page._variable_columns) == 2  # unassigned pool + the one real group


def test_auto_sort_assigns_unambiguous_requirements_and_leaves_the_rest_unassigned(qtbot, monkeypatch):
    page = MonitorExportPage(_state_for_auto_sort())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group A")
    _add_group(page, monkeypatch, "Group B")
    _move_variable_to_group(page, "a", "Group A")
    _move_variable_to_group(page, "b", "Group B")

    page._on_auto_sort_clicked()

    assert _requirement_member_texts(page, "Group A") == ["r1"]
    assert _requirement_member_texts(page, "Group B") == ["r2"]
    # r3 (spans both groups) and r4 (its only variable, "z", was never grouped) are ambiguous.
    assert set(_requirement_member_texts(page, _UNASSIGNED_REQUIREMENTS)) == {"r3", "r4"}


def test_auto_sort_without_any_group_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_for_auto_sort())
    qtbot.addWidget(page)
    page.on_show()

    page._on_auto_sort_clicked()

    assert called == [True]


def test_removing_a_variable_group_also_removes_its_requirement_group(qtbot, monkeypatch):
    page = MonitorExportPage(_state_for_auto_sort())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group A")
    _move_variable_to_group(page, "a", "Group A")
    page._on_auto_sort_clicked()
    assert _requirement_member_texts(page, "Group A") == ["r1", "r3"]  # r3's other var ("b") is unassigned, not conflicting
    group_id = _column(page, "Group A").group_id

    page._on_remove_variable_group_clicked(group_id)

    assert len(page._variable_columns) == 1
    assert page.requirement_tree.topLevelItemCount() == 1
    assert "r1" in _requirement_member_texts(page, _UNASSIGNED_REQUIREMENTS)
    assert "a" in _variable_member_texts(page, _UNASSIGNED_VARIABLES)


def test_removing_an_already_gone_group_is_a_safe_no_op(qtbot):
    """The pool column has no remove button at all (removable=False), so there's no UI path to
    trigger this with a real group_id -- this just confirms the method itself stays defensive."""
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()

    page._on_remove_variable_group_clicked(999)

    assert len(page._variable_columns) == 1


def test_renaming_a_variable_group_renames_its_requirement_group_and_export_selector(qtbot, monkeypatch):
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Original Name")
    group_id = _column(page, "Original Name").group_id
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("Renamed", True))

    page._on_rename_variable_group_clicked(group_id)

    assert page.export_group_combo.findText("Renamed") != -1
    assert page.export_group_combo.findText("Original Name") == -1
    assert _requirement_member_texts(page, "Renamed") == []
    assert _column(page, "Renamed").header_label.text() == "Renamed"


def test_renaming_a_variable_group_rejects_a_duplicate_name(qtbot, monkeypatch):
    called = []
    page = MonitorExportPage(_state_with_import())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group 1")
    _add_group(page, monkeypatch, "Group 2")
    group_2_id = _column(page, "Group 2").group_id
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("Group 1", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))

    page._on_rename_variable_group_clicked(group_2_id)

    assert called == [True]
    assert _column(page, "Group 2").name == "Group 2"  # unchanged


def test_export_group_selector_only_lists_custom_groups(qtbot, monkeypatch):
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group 1")

    names = [page.export_group_combo.itemText(i) for i in range(page.export_group_combo.count())]

    assert names == ["Group 1"]


def test_variable_column_list_drop_event_moves_the_item_between_columns(qtbot):
    """_VariableColumnList overrides dropEvent so a drag between two columns actually moves the
    item -- Qt's own cross-widget default is to copy it, leaving a duplicate behind, which this
    confirms doesn't happen. A full native drag can't be simulated headlessly, so this calls
    dropEvent directly with a minimal stand-in that provides what it actually reads
    (source()/acceptProposedAction())."""
    class _FakeDropEvent:
        def __init__(self, source):
            self._source = source
            self.accepted = False

        def source(self):
            return self._source

        def acceptProposedAction(self):
            self.accepted = True

    source_list = _VariableColumnList()
    qtbot.addWidget(source_list)
    target_list = _VariableColumnList()
    qtbot.addWidget(target_list)
    source_list.addItem("a")
    source_list.addItem("b")
    source_list.setCurrentRow(0)  # selects "a"

    event = _FakeDropEvent(source_list)
    target_list.dropEvent(event)

    assert [source_list.item(i).text() for i in range(source_list.count())] == ["b"]
    assert [target_list.item(i).text() for i in range(target_list.count())] == ["a"]
    assert event.accepted is True


# -- click-to-popup --------------------------------------------------------------------------


def test_clicking_a_requirement_shows_its_variables_in_a_tooltip(qtbot, monkeypatch):
    captured = {}
    monkeypatch.setattr(QToolTip, "showText", lambda pos, text, widget=None: captured.update(text=text))
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()
    item = page.requirement_tree.findItems("r1", Qt.MatchFlag.MatchRecursive, 0)[0]

    page._on_requirement_item_clicked(item, 0)

    assert captured["text"] == "a, b"


def test_clicking_a_group_header_does_not_show_a_tooltip(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QToolTip, "showText", lambda *a, **kw: called.append(True))
    page = MonitorExportPage(_state_with_three_requirements())
    qtbot.addWidget(page)
    page.on_show()

    page._on_requirement_item_clicked(page.requirement_tree.topLevelItem(0), 0)

    assert called == []


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
    page = MonitorExportPage(_state_for_auto_sort())
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group A")
    _add_group(page, monkeypatch, "Group B")
    _move_variable_to_group(page, "a", "Group A")
    _move_variable_to_group(page, "b", "Group B")
    page._on_auto_sort_clicked()
    page.export_group_combo.setCurrentText("Group A")
    page._output_dir = tmp_path

    page._on_generate_clicked()

    assert {s.requirement_id for s in captured["specs"]} == {"r1"}
    assert captured["output_dir"] == tmp_path / _sanitize_dirname("Group A")


@requires_ogma
def test_generate_success_updates_state(qtbot, monkeypatch, tmp_path):
    state = _state_with_import()
    page = MonitorExportPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _add_group(page, monkeypatch, "Group 1")
    _move_variable_to_group(page, "request", "Group 1")
    _move_variable_to_group(page, "grant", "Group 1")
    page._on_auto_sort_clicked()
    page._output_dir = Path(tmp_path)
    page.export_group_combo.setCurrentText("Group 1")

    page._on_generate_clicked()

    assert "generated monitor package" in page.status_label.text().lower()
    expected_dir = Path(tmp_path) / _sanitize_dirname("Group 1")
    assert state.generated_monitor_path == str(expected_dir)
    assert (expected_dir / "copilot" / "src" / "Copilot.hs").is_file()
