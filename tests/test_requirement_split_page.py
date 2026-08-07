from PySide6.QtWidgets import QMessageBox

from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.requirement_split import RequirementSplitPage


def test_editing_requirement_text_updates_state(qtbot):
    state = ProjectState()
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)

    page.requirement_edit.setPlainText("The system shall do X")

    assert state.original_requirement == "The system shall do X"


def test_add_and_remove_sub_requirement(qtbot):
    state = ProjectState()
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)

    page.new_sub_requirement_edit.setText("r1.1 text")
    page._on_add_sub_requirement()
    assert state.sub_requirements == ["r1.1 text"]
    assert page.sub_requirement_list.count() == 1

    page.sub_requirement_list.setCurrentRow(0)
    page._on_remove_selected()
    assert state.sub_requirements == []
    assert page.sub_requirement_list.count() == 0


def test_split_without_requirement_warns_instead_of_crashing(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: called.append(True))
    state = ProjectState()
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)

    page._on_split_clicked()

    assert called == [True]


def test_split_reports_not_implemented(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    state = ProjectState(original_requirement="text")
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)

    page._on_split_clicked()

    assert called == [True]
