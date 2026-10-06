from PySide6.QtWidgets import QMessageBox

from ltlsplitter.core.models import FretImport, FretRequirement, SplitSuggestion, SubFormula, Variable, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.import_split import ImportSplitPage


def _state_with_import() -> ProjectState:
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


def test_on_show_lists_imported_requirements(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)

    page.on_show()

    assert page.requirement_list.count() == 1


def test_requirement_list_shows_only_the_id(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)

    page.on_show()

    item = page.requirement_list.item(0)
    assert item.text() == "r1"
    assert item.toolTip() == "the system shall..."


def test_selecting_requirement_shows_formula_and_variables(qtbot):
    state = _state_with_import()
    page = ImportSplitPage(state)
    qtbot.addWidget(page)
    page.on_show()

    page.requirement_list.setCurrentRow(0)

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
    page.requirement_list.setCurrentRow(0)

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
    page.requirement_list.setCurrentRow(0)

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
    page.requirement_list.setCurrentRow(0)
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
    page.requirement_list.setCurrentRow(0)
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
    page.requirement_list.setCurrentRow(0)

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
    page.requirement_list.setCurrentRow(0)
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
    page.requirement_list.setCurrentRow(0)
    state.split_accepted = True
    state.sub_formulas = [SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)")]

    page._on_reject_clicked()

    assert state.split_accepted is False
    assert [s.id for s in state.active_sub_formulas()] == ["r1"]
