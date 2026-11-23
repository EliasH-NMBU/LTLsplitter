import csv
from datetime import datetime

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from ltlsplitter.core.evaluation_log import (
    COLUMNS,
    EVALUATION_FILE_NAME,
    append_evaluation,
    evaluation_row,
    use_case_folder_name,
)
from ltlsplitter.core.models import DecompositionValidation, FretRequirement, SubFormula, ToolCheckResult
from ltlsplitter.core.project_state import ProjectState
from ltlsplitter.gui.pages.decomposition_validation import DecompositionValidationPage
from ltlsplitter.gui.pages.import_split import ImportSplitPage

_REQ = FretRequirement(reqid="r1\t", fulltext="", pt_formula="(H (p -> (a & b)))", ft_formula="(G (p -> (a & b)))")
_SUBS = [SubFormula("r1.1", "(H (p -> a))", "(G (p -> a))"), SubFormula("r1.2", "(H (p -> b))", "(G (p -> b))")]


def _validation(spin_status="pass", nd_spot_status="pass") -> DecompositionValidation:
    eq = [ToolCheckResult("nuXmv", True, status="pass"), ToolCheckResult("Spot", True, status="pass"),
          ToolCheckResult("SPIN", spin_status == "pass", status=spin_status)]
    nd = {s.id: [ToolCheckResult("nuXmv", True, status="pass"),
                 ToolCheckResult("Spot", nd_spot_status == "pass" or s.id == "r1.1", status="pass" if s.id == "r1.1" else nd_spot_status),
                 ToolCheckResult("SPIN", True, status="pass")] for s in _SUBS}
    return DecompositionValidation(equivalence=eq, nondegeneracy=nd)


def test_use_case_folder_name_comes_from_the_project_name():
    assert use_case_folder_name("VALU3S Use Case 6") == "VALU3S_Use_Case_6"
    assert use_case_folder_name("", "/x/model.smv") == "model"
    assert use_case_folder_name("  ") == "unnamed_use_case"


def test_evaluation_row_complexity_columns():
    row = evaluation_row("UC", _REQ, _SUBS, _validation(), declared_names={"p", "a", "b"},
                         timestamp=datetime(2026, 11, 23, 12, 0))
    # original: H, ->, & = 3 operators + 0.5 * 3 variables = 4.5 ; each part: H, -> = 2 + 1 = 3
    assert row["requirement_id"] == "r1"
    assert row["sub_requirement_count"] == 2
    assert row["sub_requirement_ids"] == "r1.1 r1.2"
    assert (row["original_complexity_pt"], row["decomp_total_complexity_pt"], row["decomp_mean_complexity_pt"],
            row["decomp_max_complexity_pt"]) == (4.5, 6.0, 3.0, 3.0)
    assert (row["delta_total_complexity_pt"], row["delta_mean_complexity_pt"]) == (1.5, -1.5)
    assert row["delta_total_complexity_ft"] == 1.5
    assert row["timestamp"] == "2026-11-23T12:00:00"


def test_evaluation_row_tool_statuses_distinguish_fail_and_error():
    row = evaluation_row("UC", _REQ, _SUBS, _validation(spin_status="error", nd_spot_status="fail"))
    assert (row["soundness_nuxmv"], row["soundness_spot"], row["soundness_spin"]) == ("PASS", "PASS", "ERROR")
    assert row["semantic_spread_nuxmv"] == "PASS"
    assert row["semantic_spread_spot"] == "FAIL (r1.2)"
    assert row["all_checks_passed"] is False


def test_append_evaluation_writes_header_once_and_appends(tmp_path):
    row = evaluation_row("UC", _REQ, _SUBS, _validation())
    append_evaluation(tmp_path, row)
    append_evaluation(tmp_path, row)

    with (tmp_path / EVALUATION_FILE_NAME).open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert tuple(rows[0].keys()) == COLUMNS
    assert rows[1]["soundness_spin"] == "PASS"


# -- GUI: folder on import, save location, logging on validate -------------------------------


def _write_fret(tmp_path):
    import json
    path = tmp_path / "in" / "uc.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "requirements": [{"reqid": "r1", "project": "My Use Case", "fulltext": "",
                          "semantics": {"pt": _REQ.pt_formula, "ft": _REQ.ft_formula, "variables": ["p", "a", "b"]}}],
        "variables": [{"variable_name": n, "dataType": "boolean", "idType": "Input"} for n in "pab"],
    }))
    return path


def test_import_creates_the_use_case_folder_and_first_split_is_saved_there(qtbot, monkeypatch, tmp_path):
    source = _write_fret(tmp_path)
    page = ImportSplitPage(ProjectState())
    qtbot.addWidget(page)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(source), ""))
    page._on_import_clicked()

    folder = tmp_path / "data" / "My_Use_Case"
    assert folder.is_dir()
    assert page.state.use_case_dir == str(folder)
    assert "My_Use_Case" in page.data_root_label.text()

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **kw: ("r1_split", True))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
    page._save_split(page.state.fret_import.requirement("r1"), _SUBS)

    assert (folder / "r1_split.json").is_file()
    assert page.state.session_export_path == str(folder / "r1_split.json")


def test_changing_the_data_root_moves_the_use_case_folder(qtbot, monkeypatch, tmp_path):
    source = _write_fret(tmp_path)
    page = ImportSplitPage(ProjectState())
    qtbot.addWidget(page)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **kw: (str(source), ""))
    page._on_import_clicked()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **kw: str(tmp_path / "elsewhere"))

    page._on_change_data_root_clicked()

    assert page.state.use_case_dir == str(tmp_path / "elsewhere" / "My_Use_Case")


def test_validate_appends_a_row_for_a_split(qtbot, monkeypatch, tmp_path):
    from ltlsplitter.core.models import FretImport, Variable, VariableType

    children = [FretRequirement(s.id, "", s.pt_formula, s.ft_formula, parent_reqid="r1") for s in _SUBS]
    state = ProjectState(
        fret_import=FretImport("p", [FretRequirement("r1", "", _REQ.pt_formula, _REQ.ft_formula), *children],
                               [Variable(n, VariableType.BOOL) for n in "pab"]),
        selected_requirement_id="r1", use_case_dir=str(tmp_path / "uc"),
    )
    monkeypatch.setattr("ltlsplitter.gui.pages.decomposition_validation.validate_decomposition",
                        lambda *a, **kw: _validation())
    page = DecompositionValidationPage(state)
    qtbot.addWidget(page)

    page._on_validate_clicked()
    page._on_validate_clicked()

    with (tmp_path / "uc" / EVALUATION_FILE_NAME).open() as handle:
        rows = list(csv.DictReader(handle))
    assert [r["requirement_id"] for r in rows] == ["r1", "r1"]
    assert rows[0]["sub_requirement_count"] == "2"
    assert "Logged to" in page.log_label.text()


def test_validate_does_not_log_an_unsplit_requirement(qtbot, monkeypatch, tmp_path):
    from ltlsplitter.core.models import FretImport

    state = ProjectState(fret_import=FretImport("p", [FretRequirement("r1", "", "(H a)", "(G a)")]),
                         selected_requirement_id="r1", use_case_dir=str(tmp_path / "uc"))
    monkeypatch.setattr("ltlsplitter.gui.pages.decomposition_validation.validate_decomposition",
                        lambda *a, **kw: _validation())
    page = DecompositionValidationPage(state)
    qtbot.addWidget(page)

    page._on_validate_clicked()

    assert not (tmp_path / "uc" / EVALUATION_FILE_NAME).exists()
    assert "isn't split" in page.log_label.text()
