"""Page 1's New Requirement / Edit Requirement / Add Variable / Save, and their pop-ups."""

import json

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.models import Formalization, FretRequirement, VariableRole, VariableType
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.dialogs import RequirementDialog, VariableDialog
from ltlsplitter.gui.pages.import_split import ImportSplitPage


def _write_fret_file(tmp_path) -> str:
    data = {
        "requirements": [{
            "reqid": "r1", "fulltext": "the system shall...", "project": "demo",
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


def _page(qtbot, monkeypatch, tmp_path) -> ImportSplitPage:
    source = _write_fret_file(tmp_path)
    page = ImportSplitPage(ProjectState(fret_import=import_fret_file(source), fret_import_path=source))
    qtbot.addWidget(page)
    page.on_show()
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("session", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    return page


def _export(tmp_path) -> dict:
    return json.loads((tmp_path / "ltlsplitter_exports" / "session.json").read_text())


def _fake_exec(fill):
    def _exec(dialog):
        fill(dialog)
        dialog.accept()
        return QDialog.DialogCode.Accepted if dialog.result() == QDialog.DialogCode.Accepted else QDialog.DialogCode.Rejected
    return _exec


# -- edit / new requirement ------------------------------------------------------------------


def test_editing_a_main_requirement_is_saved_to_the_session_file(qtbot, monkeypatch, tmp_path):
    page = _page(qtbot, monkeypatch, tmp_path)
    page._select_requirement_item("r1")

    def fill(dialog):
        assert dialog.reqid_edit.isReadOnly()  # renaming would orphan sub-formulas
        dialog.text_edit.setPlainText("edited")
        dialog.pt_edit.setPlainText("(H (a & b))")
        dialog.ft_edit.setPlainText("(G (a & b))")

    monkeypatch.setattr(RequirementDialog, "exec", _fake_exec(fill))
    page._on_edit_requirement_clicked()

    saved = _export(tmp_path)["requirements"][0]
    assert saved["fulltext"] == "edited"
    assert saved["semantics"]["pt"] == "(H (a & b))"
    assert page.state.fret_import.requirement("r1").ft_formula == "(G (a & b))"
    assert "(H (a & b))" in page.formula_label.text()
    assert "Saved to" in page.save_status_label.text()
    # original untouched
    assert json.loads(open(page.state.fret_import_path.replace("ltlsplitter_exports/session.json", "source.json")).read())[
        "requirements"][0]["semantics"]["pt"] == "(H (a -> b))"


def test_new_requirement_from_natural_language_uses_the_llm_and_is_saved(qtbot, monkeypatch, tmp_path):
    page = _page(qtbot, monkeypatch, tmp_path)
    seen = {}

    def fake_formalize(text, variables, examples, api_key=None):
        seen["text"], seen["variables"], seen["examples"] = text, [v.name for v in variables], examples
        return Formalization(pt_formula="(H (a -> (! b)))", ft_formula="(G (a -> (! b)))", notes="")

    monkeypatch.setattr("ltlsplitter.gui.dialogs.formalize", fake_formalize)

    def fill(dialog):
        assert dialog.reqid() == "req_2"
        dialog.text_edit.setPlainText("When a holds, b shall be off.")
        dialog._on_translate_clicked()
        qtbot.waitUntil(lambda: dialog._llm_thread is None, timeout=5000)
        assert dialog.pt_formula() == "(H (a -> (! b)))"

    monkeypatch.setattr(RequirementDialog, "exec", _fake_exec(fill))
    page._on_new_requirement_clicked()

    assert seen["text"] == "When a holds, b shall be off."
    assert seen["variables"] == ["a", "b"]
    assert [e.reqid for e in seen["examples"]] == ["r1"]
    req = page.state.fret_import.requirement("req_2")
    assert (req.fulltext, req.ft_formula, req.variable_names) == ("When a holds, b shall be off.", "(G (a -> (! b)))", ["a", "b"])
    assert [r["reqid"] for r in _export(tmp_path)["requirements"]] == ["r1", "req_2"]
    assert page.state.selected_requirement_id == "req_2"


def test_requirement_dialog_rejects_duplicate_ids_and_empty_formulas(qtbot, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: warnings.append(a[2]))
    dialog = RequirementDialog(variables=[], existing_reqids={"r1"}, default_reqid="r1")
    qtbot.addWidget(dialog)

    dialog.accept()
    assert "already exists" in warnings[-1]

    dialog.reqid_edit.setText("r2")
    dialog.accept()
    assert "at least one formula" in warnings[-1]
    assert dialog.result() != QDialog.DialogCode.Accepted


def test_requirement_dialog_flags_undeclared_identifiers(qtbot):
    from ltlsplitter.core.models import Variable

    dialog = RequirementDialog(variables=[Variable(name="a", type=VariableType.BOOL)], existing_reqids=set())
    qtbot.addWidget(dialog)
    dialog.pt_edit.setPlainText("(H (a -> speed_ok))")
    assert "speed_ok" in dialog.check_label.text()


# -- add variable ----------------------------------------------------------------------------


def test_add_variable_popup_is_saved_with_its_parameters(qtbot, monkeypatch, tmp_path):
    page = _page(qtbot, monkeypatch, tmp_path)

    def fill(dialog):
        dialog.name_edit.setText("speed")
        dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(VariableType.FLOAT))
        dialog.min_edit.setText("0")
        dialog.max_edit.setText("12.5")
        dialog.topic_edit.setText("/odom/speed")

    monkeypatch.setattr(VariableDialog, "exec", _fake_exec(fill))
    page._on_add_variable_clicked()

    saved = {v["variable_name"]: v for v in _export(tmp_path)["variables"]}
    assert saved["speed"]["dataType"] == "double"
    assert saved["speed"]["idType"] == "Input"
    assert (saved["speed"]["min_value"], saved["speed"]["max_value"], saved["speed"]["topic"]) == (0.0, 12.5, "/odom/speed")
    assert "speed" in {v.name for v in page.state.fret_import.variables}


def test_variable_dialog_validation(qtbot, monkeypatch):
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: warnings.append(a[2]))
    dialog = VariableDialog(existing_names={"a"})
    qtbot.addWidget(dialog)

    for name, expected in (("1x", "identifier"), ("G", "keyword"), ("a", "already exists")):
        dialog.name_edit.setText(name)
        dialog.accept()
        assert expected in warnings[-1]

    dialog.name_edit.setText("mode")
    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(VariableType.ENUM))
    dialog.accept()
    assert "at least one value" in warnings[-1]

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(VariableType.INT))
    dialog.min_edit.setText("5")
    dialog.max_edit.setText("1")
    dialog.accept()
    assert "larger than maximum" in warnings[-1]

    dialog.type_combo.setCurrentIndex(dialog.type_combo.findData(VariableType.BOOL))
    dialog.role_combo.setCurrentIndex(dialog.role_combo.findData(VariableRole.INTERNAL))
    dialog.accept()
    assert "defining expression" in warnings[-1]

    dialog.assignment_edit.setText("x > 3")
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    var = dialog.variable()
    assert (var.name, var.role, var.assignment, var.topic) == ("mode", VariableRole.INTERNAL, "x > 3", "")


def test_adding_a_variable_from_the_requirement_dialog_clears_the_undeclared_warning(qtbot, monkeypatch, tmp_path):
    page = _page(qtbot, monkeypatch, tmp_path)
    monkeypatch.setattr(VariableDialog, "exec", _fake_exec(lambda d: None))  # accepts the suggested name

    dialog = page._requirement_dialog(None)
    qtbot.addWidget(dialog)
    dialog.pt_edit.setPlainText("(H (a -> halt))")
    assert "halt" in dialog.check_label.text()

    dialog._on_add_variable_clicked()

    assert "Possibly undeclared" not in dialog.check_label.text()
    assert "halt" in {v["variable_name"] for v in _export(tmp_path)["variables"]}


# -- save button / re-split -----------------------------------------------------------------


def test_save_button_writes_deletions_and_assumption_changes(qtbot, monkeypatch, tmp_path):
    page = _page(qtbot, monkeypatch, tmp_path)
    page.state.fret_import.requirements.append(FretRequirement(reqid="r2", fulltext="", pt_formula="(H a)", ft_formula="(G a)"))
    page._set_all_assumptions(True)
    page.state.fret_import.requirements = [r for r in page.state.fret_import.requirements if r.reqid != "r2"]

    page.save_button.click()

    saved = _export(tmp_path)["requirements"]
    assert [r["reqid"] for r in saved] == ["r1"]
    assert saved[0]["is_assumption"] is True


def test_resplitting_replaces_the_previous_sub_formulas(qtbot, monkeypatch, tmp_path):
    from ltlsplitter.core.models import SubFormula

    page = _page(qtbot, monkeypatch, tmp_path)
    parent = page.state.fret_import.requirement("r1")
    page._save_split(parent, [SubFormula("r1.1", "(H a)", "(G a)"), SubFormula("r1.2", "(H b)", "(G b)")])
    parent = page.state.fret_import.requirement("r1")
    page._save_split(parent, [SubFormula("r1.1", "(H (a -> b))", "(G (a -> b))")])

    reqids = [r["reqid"] for r in _export(tmp_path)["requirements"]]
    assert reqids == ["r1", "r1.1"]
