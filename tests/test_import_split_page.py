import json

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox

from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.models import FretImport, FretRequirement, SplitSuggestion, SubFormula, Variable, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.import_split import ImportSplitPage


def _state_with_import() -> ProjectState:
    """No fret_import_path -- _save_split's guard no-ops on this, so tests using it never hit
    the QInputDialog/file-I/O save flow (that's exercised separately, with a real temp file)."""
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(
                reqid="r1", fulltext="the system shall...",
                pt_formula="(H (a -> b))", ft_formula="(G (a -> b))", variable_names=["a", "b"],
            ),
        ],
        variables=[Variable(name="a", type=VariableType.BOOL), Variable(name="b", type=VariableType.BOOL)],
    )
    return ProjectState(fret_import=fret_import)


def _write_fret_file(tmp_path, reqid="r1", fulltext="the system shall...") -> str:
    data = {
        "requirements": [{
            "reqid": reqid, "fulltext": fulltext, "project": "demo",
            "semantics": {"pt": "(H (a -> b))", "ft": "(G (a -> b))", "variables": ["a", "b"]},
        }],
        "variables": [
            {"variable_name": "a", "dataType": "boolean", "idType": "Input"},
            {"variable_name": "b", "dataType": "boolean", "idType": "Output"},
        ],
    }
    path = tmp_path / "source.json"
    path.write_text(json.dumps(data))
    return str(path)


def _select(page: ImportSplitPage, reqid: str) -> None:
    page._select_requirement_item(reqid)


def _isolated_page(monkeypatch, tmp_path, state=None) -> ImportSplitPage:
    """Points the page's QSettings at a throwaway ini file instead of this machine's real,
    persisted LTLsplitter settings -- without this, the API key toggle tests below would depend
    on whatever key (if any) a real user previously saved outside of tests. Also shows the page:
    isVisible() only reflects setVisible() once a widget's ancestor chain has actually been
    shown (same reason test_force_split_button_hidden_* below call page.show()), not just after
    being registered with qtbot.addWidget."""
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.QSettings",
        lambda *a, **kw: QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat),
    )
    page = ImportSplitPage(state if state is not None else ProjectState())
    page.show()
    return page


# -- API key visibility toggle --------------------------------------------------------------


def test_api_key_field_starts_visible_with_no_saved_key(qtbot, monkeypatch, tmp_path):
    page = _isolated_page(monkeypatch, tmp_path)
    qtbot.addWidget(page)

    assert page.api_key_edit.isVisible()
    assert not page.api_key_status_label.isVisible()
    assert not page.api_key_change_button.isVisible()
    assert page.api_key_status_label.text() == "No API key set"


def test_api_key_field_collapses_once_a_key_is_entered(qtbot, monkeypatch, tmp_path):
    page = _isolated_page(monkeypatch, tmp_path)
    qtbot.addWidget(page)

    page.api_key_edit.setText("sk-ant-test123")
    page._on_api_key_editing_finished()

    assert not page.api_key_edit.isVisible()
    assert page.api_key_status_label.isVisible()
    assert page.api_key_status_label.text() == "API key set"
    assert page.api_key_change_button.isVisible()
    assert page.api_key_change_button.text() == "Change"


def test_empty_key_on_editing_finished_stays_in_editing_mode(qtbot, monkeypatch, tmp_path):
    """Nothing to hide behind a "key set" button if the field was left empty."""
    page = _isolated_page(monkeypatch, tmp_path)
    qtbot.addWidget(page)

    page.api_key_edit.setText("")
    page._on_api_key_editing_finished()

    assert page.api_key_edit.isVisible()
    assert not page.api_key_status_label.isVisible()


def test_change_button_reopens_the_edit_field(qtbot, monkeypatch, tmp_path):
    page = _isolated_page(monkeypatch, tmp_path)
    qtbot.addWidget(page)
    page.api_key_edit.setText("sk-ant-test123")
    page._on_api_key_editing_finished()
    assert not page.api_key_edit.isVisible()

    page._on_api_key_change_clicked()

    assert page.api_key_edit.isVisible()
    assert not page.api_key_status_label.isVisible()
    assert page.api_key_edit.text() == "sk-ant-test123"


def test_api_key_field_starts_collapsed_when_a_key_was_already_saved(qtbot, monkeypatch, tmp_path):
    """A key saved in an earlier session (QSettings persists across runs) must not be shown in
    plain/masked form on screen just because the page was freshly constructed."""
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("anthropic/api_key", "sk-ant-preexisting")
    settings.sync()

    page = _isolated_page(monkeypatch, tmp_path)
    qtbot.addWidget(page)

    assert not page.api_key_edit.isVisible()
    assert page.api_key_status_label.isVisible()
    assert page.api_key_status_label.text() == "API key set"


def test_on_show_lists_imported_requirements(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert page.requirement_tree.topLevelItemCount() == 1


def test_requirement_list_shows_only_the_id(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)

    page.on_show()

    item = page.requirement_tree.topLevelItem(0)
    assert item.text(0) == "r1"
    assert item.toolTip(0) == "the system shall..."


def test_selecting_requirement_shows_formula_and_variables(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()

    _select(page, "r1")

    assert state.selected_requirement_id == "r1"
    assert "(H (a -> b))" in page.formula_label.text()
    assert "a" in page.variables_label.text() and "b" in page.variables_label.text()


def test_accept_without_suggestion_shows_message(qtbot, monkeypatch):
    called = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: called.append(True))
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")

    page._on_accept_clicked()

    assert called == [True]


def test_suggest_split_populates_suggestion(qtbot, monkeypatch):
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.suggest_split",
        lambda pt, ft, api_key=None: SplitSuggestion(should_split=True, rationale="two obligations", suggested_count=2),
    )
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")

    page._on_suggest_clicked()

    assert state.split_suggestion.should_split is True
    assert "two obligations" in page.suggestion_label.text()


def test_accept_decomposes_and_populates_sub_formulas(qtbot, monkeypatch):
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.decompose",
        lambda parent_id, pt, ft, count, api_key=None, feedback=None: [
            SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
            SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)"),
        ],
    )
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")
    state.split_suggestion = SplitSuggestion(should_split=True, rationale="x", suggested_count=2)

    page._on_accept_clicked()

    assert state.split_accepted is True
    assert len(state.sub_formulas) == 2
    assert page.sub_formula_list.count() == 2


def test_force_split_button_hidden_until_llm_recommends_against_splitting(qtbot, monkeypatch):
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.suggest_split",
        lambda pt, ft, api_key=None: SplitSuggestion(should_split=False, rationale="already atomic", suggested_count=1),
    )
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.show()
    page.on_show()
    _select(page, "r1")
    assert not page.force_split_button.isVisible()

    page._on_suggest_clicked()

    assert page.force_split_button.isVisible()


def test_force_split_button_hidden_when_llm_recommends_splitting(qtbot, monkeypatch):
    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.suggest_split",
        lambda pt, ft, api_key=None: SplitSuggestion(should_split=True, rationale="two obligations", suggested_count=2),
    )
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.show()
    page.on_show()
    _select(page, "r1")

    page._on_suggest_clicked()

    assert not page.force_split_button.isVisible()


def test_force_split_requests_a_split_from_the_llm_even_though_none_was_recommended(qtbot, monkeypatch):
    captured = {}

    def fake_decompose(parent_id, pt, ft, count, api_key=None, feedback=None):
        captured["count"] = count
        return [
            SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
            SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)"),
        ]

    monkeypatch.setattr("ltlsplitter.gui.pages.import_split.decompose", fake_decompose)
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")
    state.split_suggestion = SplitSuggestion(should_split=False, rationale="already atomic", suggested_count=1)

    page._on_force_split_clicked()

    assert captured["count"] == 2
    assert state.split_accepted is True
    assert len(state.sub_formulas) == 2


def test_reject_keeps_original_as_active_formula(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")
    state.split_accepted = True
    state.sub_formulas = [SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)")]

    page._on_reject_clicked()

    assert state.split_accepted is False
    assert [s.id for s in state.active_sub_formulas()] == ["r1"]


# -- assumption checkbox ------------------------------------------------------------------


def _state_with_two_requirements() -> ProjectState:
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(reqid="r1", fulltext="...", pt_formula="(H a)", ft_formula="(G a)"),
            FretRequirement(reqid="r2", fulltext="...", pt_formula="(H b)", ft_formula="(G b)"),
        ],
        variables=[Variable(name="a", type=VariableType.BOOL), Variable(name="b", type=VariableType.BOOL)],
    )
    return ProjectState(fret_import=fret_import)


def test_toggling_assumption_checkbox_updates_the_requirement(qtbot):
    state = _state_with_two_requirements()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()

    item = page.requirement_tree.topLevelItem(0)
    item.setCheckState(1, Qt.CheckState.Checked)

    assert state.fret_import.requirement("r1").is_assumption is True
    assert state.fret_import.requirement("r2").is_assumption is False


def test_select_all_marks_every_requirement_as_assumption(qtbot):
    state = _state_with_two_requirements()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page._set_all_assumptions(True)

    assert state.fret_import.requirement("r1").is_assumption is True
    assert state.fret_import.requirement("r2").is_assumption is True
    for i in range(page.requirement_tree.topLevelItemCount()):
        assert page.requirement_tree.topLevelItem(i).checkState(1) == Qt.CheckState.Checked


def test_clear_all_marks_every_requirement_as_not_assumption(qtbot):
    state = _state_with_two_requirements()
    for req in state.fret_import.requirements:
        req.is_assumption = True
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page._set_all_assumptions(False)

    assert state.fret_import.requirement("r1").is_assumption is False
    assert state.fret_import.requirement("r2").is_assumption is False


# -- save-as-new-file flow (real temp files, QInputDialog mocked to avoid a real modal) -------


def test_accept_saves_split_as_new_file_nested_under_parent(qtbot, monkeypatch, tmp_path):
    source_path = _write_fret_file(tmp_path)
    state = ProjectState(fret_import=import_fret_file(source_path), fret_import_path=source_path)
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")
    state.split_suggestion = SplitSuggestion(should_split=True, rationale="x", suggested_count=2)

    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.decompose",
        lambda parent_id, pt, ft, count, api_key=None, feedback=None: [
            SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
            SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)"),
        ],
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("r1_split", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)

    page._on_accept_clicked()

    export_path = tmp_path / "ltlsplitter_exports" / "r1_split.json"
    assert export_path.is_file()
    assert state.fret_import_path == str(export_path)
    assert len(state.fret_import.requirements) == 3
    child = state.fret_import.requirement("r1.1")
    assert child is not None
    assert child.parent_reqid == "r1"

    parent_item = page.requirement_tree.topLevelItem(0)
    assert parent_item.text(0) == "r1"
    assert parent_item.childCount() == 2

    # the original source file must be untouched
    original = json.loads(open(source_path).read())
    assert len(original["requirements"]) == 1


def test_accept_skips_save_when_dialog_cancelled(qtbot, monkeypatch, tmp_path):
    source_path = _write_fret_file(tmp_path)
    state = ProjectState(fret_import=import_fret_file(source_path), fret_import_path=source_path)
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()
    _select(page, "r1")
    state.split_suggestion = SplitSuggestion(should_split=True, rationale="x", suggested_count=2)

    monkeypatch.setattr(
        "ltlsplitter.gui.pages.import_split.decompose",
        lambda parent_id, pt, ft, count, api_key=None, feedback=None: [
            SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
        ],
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("", False))

    page._on_accept_clicked()

    assert state.fret_import_path == source_path
    assert not (tmp_path / "ltlsplitter_exports").exists()
    # the split itself still happened in memory -- only saving was skipped
    assert state.split_accepted is True
    assert len(state.sub_formulas) == 1
