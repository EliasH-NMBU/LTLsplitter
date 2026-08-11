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


def test_split_without_api_key_prompts_for_one(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    state = ProjectState(original_requirement="text")
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)

    page._on_split_clicked()

    assert called == [True]


def test_split_success_populates_state(qtbot, monkeypatch):
    from ltlsplitter.core.models import RequirementSplit

    monkeypatch.setattr(
        "ltlsplitter.gui.pages.requirement_split.split_requirement",
        lambda requirement, api_key=None: RequirementSplit(
            original=requirement, sub_requirements=["r1.1 text", "r1.2 text"]
        ),
    )
    state = ProjectState(original_requirement="text")
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)
    page.api_key_edit.setText("sk-ant-fake-key")

    page._on_split_clicked()

    assert state.sub_requirements == ["r1.1 text", "r1.2 text"]
    assert page.sub_requirement_list.count() == 2


def test_split_failure_shows_error(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: called.append(True))
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.requirement_split.split_requirement",
        lambda requirement, api_key=None: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    state = ProjectState(original_requirement="text")
    page = RequirementSplitPage(state)
    qtbot.addWidget(page)
    page.api_key_edit.setText("sk-ant-fake-key")

    page._on_split_clicked()

    assert called == [True]


def test_api_key_persists_across_page_instances(qtbot):
    state = ProjectState()
    page1 = RequirementSplitPage(state)
    qtbot.addWidget(page1)
    page1.api_key_edit.setText("sk-ant-saved-key")

    page2 = RequirementSplitPage(state)
    qtbot.addWidget(page2)

    assert page2.api_key_edit.text() == "sk-ant-saved-key"
