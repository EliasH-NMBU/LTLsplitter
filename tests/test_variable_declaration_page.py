from PySide6.QtWidgets import QMessageBox

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.variable_declaration import VariableDeclarationPage


def test_add_variable_appends_to_state_and_table(qtbot):
    state = ProjectState()
    page = VariableDeclarationPage(state)
    qtbot.addWidget(page)

    page.name_edit.setText("speed")
    page.ros_node_edit.setText("/drive_node")
    page.type_combo.setCurrentText("float")
    page.min_spin.setValue(0)
    page.max_spin.setValue(10)
    page._on_add_variable()

    assert len(state.variables) == 1
    assert state.variables[0].name == "speed"
    assert state.variables[0].min_value == 0
    assert state.variables[0].max_value == 10
    assert page.table.rowCount() == 1


def test_enum_variable_stores_values(qtbot):
    state = ProjectState()
    page = VariableDeclarationPage(state)
    qtbot.addWidget(page)

    page.name_edit.setText("mode")
    page.ros_node_edit.setText("/planner")
    page.type_combo.setCurrentText("enum")
    page.enum_values_edit.setText("idle, active, error")
    page._on_add_variable()

    assert state.variables[0].enum_values == ["idle", "active", "error"]


def test_add_variable_requires_name_and_node(qtbot, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: None)
    state = ProjectState()
    page = VariableDeclarationPage(state)
    qtbot.addWidget(page)

    page._on_add_variable()

    assert state.variables == []


def test_remove_selected_removes_from_state(qtbot):
    state = ProjectState()
    page = VariableDeclarationPage(state)
    qtbot.addWidget(page)

    page.name_edit.setText("speed")
    page.ros_node_edit.setText("/drive_node")
    page._on_add_variable()
    page.table.selectRow(0)
    page._on_remove_selected()

    assert state.variables == []
    assert page.table.rowCount() == 0
