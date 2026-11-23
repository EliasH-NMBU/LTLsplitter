import json
from pathlib import Path

import pytest

from ltlsplitter.core.fret_import import (
    InvalidFretFileError,
    _normalize_type_field,
    import_fret_file,
    save_session,
)
from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableRole, VariableType

_FIXTURE = Path(__file__).parent / "fixtures" / "sRobotFRETfile.json"


def test_import_fret_file_parses_requirements_and_variables():
    result = import_fret_file(_FIXTURE)

    assert result.project == "sRobot"
    assert len(result.requirements) == 13
    assert len(result.variables) == 9

    req = result.requirement("state_req101")
    assert req is not None
    assert req.pt_formula == "(H ((classifier = 1) -> (dgt_7 -> (state = 1))))"
    assert req.ft_formula == "(G ((classifier = 1) -> (dgt_7 -> (state = 1))))"  # ftInfAUExpanded
    assert set(req.variable_names) == {"classifier", "dgt_7", "state"}


def test_import_fret_file_maps_variable_roles_and_types():
    result = import_fret_file(_FIXTURE)
    by_name = {v.name: v for v in result.variables}

    assert by_name["classifier"].role == VariableRole.INPUT
    assert by_name["classifier"].type == VariableType.INT
    assert by_name["alert"].role == VariableRole.OUTPUT
    assert by_name["alert"].type == VariableType.BOOL
    assert by_name["dgt_3"].role == VariableRole.INTERNAL
    assert by_name["dgt_3"].assignment == "distance_to_target > 3"
    assert by_name["dgt_3"].copilot_assignment == "distance_to_target > constant 3"


def test_import_fret_file_rejects_unrelated_json(tmp_path):
    bogus = tmp_path / "not_fret.json"
    bogus.write_text('{"foo": "bar"}')

    with pytest.raises(InvalidFretFileError):
        import_fret_file(bogus)


def test_import_fret_file_rejects_missing_file(tmp_path):
    with pytest.raises(InvalidFretFileError):
        import_fret_file(tmp_path / "does_not_exist.json")


def test_normalize_type_field_unwraps_a_single_element_list():
    """Confirmed against real FRET exports (the FiniteStateMachine and LiquidMixer case studies
    shipped with FRET itself): a variable's dataType/idType can be a single-element list
    (e.g. ["double"]) instead of a bare string. Using it directly as a dict key raised
    TypeError (list is unhashable) before this normalization existed."""
    assert _normalize_type_field(["double"]) == "double"
    assert _normalize_type_field("double") == "double"
    assert _normalize_type_field(None) == ""
    assert _normalize_type_field([]) == ""


def test_import_fret_file_heuristically_flags_assumption_named_requirements():
    """FRET's export has no structural assumption/guarantee field -- only this naming
    convention, confirmed against the real sRobot fixture's "dtt_assumption" requirement."""
    result = import_fret_file(_FIXTURE)
    by_reqid = {r.reqid: r for r in result.requirements}

    assert by_reqid["dtt_assumption"].is_assumption is True
    assert by_reqid["state_req101"].is_assumption is False


def _write_source(tmp_path) -> Path:
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "requirements": [
            {"reqid": "r1", "parent_reqid": "", "project": "demo", "fulltext": "...", "rationale": "keep me",
             "semantics": {"pt": "(H a)", "ptExpanded": "(H a)", "ft": "(G a)", "CoCoSpecCode": "old",
                           "variables": ["a"]}},
            {"reqid": "r2", "parent_reqid": "", "project": "demo", "fulltext": "second",
             "semantics": {"pt": "(H b)", "ft": "(G b)", "variables": ["b"]}},
        ],
        "variables": [
            {"variable_name": "a", "dataType": ["boolean"], "idType": "Input", "reqs": ["r1"]},
            {"variable_name": "b", "dataType": "boolean", "idType": "Output"},
        ],
    }))
    return source


def test_save_session_round_trips_is_assumption(tmp_path):
    """A user-toggled is_assumption must survive a save -- otherwise the checkbox would appear
    to work in the GUI, then evaporate the moment the session is written."""
    source = _write_source(tmp_path)
    fret_import = import_fret_file(source)
    fret_import.requirement("r1").is_assumption = True
    output = tmp_path / "copy.json"

    save_session(fret_import, output, source_path=source)

    assert import_fret_file(output).requirement("r1").is_assumption is True


def test_save_session_writes_an_edited_main_requirement(tmp_path):
    source = _write_source(tmp_path)
    fret_import = import_fret_file(source)
    req = fret_import.requirement("r1")
    req.fulltext = "edited text"
    req.pt_formula, req.ft_formula, req.variable_names = "(H (a & b))", "(G (a & b))", ["a", "b"]
    output = tmp_path / "copy.json"

    save_session(fret_import, output, source_path=source)

    reimported = import_fret_file(output).requirement("r1")
    assert (reimported.fulltext, reimported.pt_formula, reimported.ft_formula) == (
        "edited text", "(H (a & b))", "(G (a & b))")
    assert reimported.variable_names == ["a", "b"]
    entry = json.loads(output.read_text())["requirements"][0]
    assert entry["rationale"] == "keep me"  # FRET's own fields survive
    assert entry["ltlsplitter_edited"] is True  # flags CoCoSpecCode etc. as stale
    # the source is only read
    assert json.loads(source.read_text())["requirements"][0]["semantics"]["pt"] == "(H a)"


def test_save_session_leaves_untouched_entries_as_fret_wrote_them(tmp_path):
    source = _write_source(tmp_path)
    output = tmp_path / "copy.json"

    save_session(import_fret_file(source), output, source_path=source)

    original, saved = json.loads(source.read_text()), json.loads(output.read_text())
    assert saved["variables"] == original["variables"]
    r2_saved = saved["requirements"][1]
    assert r2_saved["semantics"] == original["requirements"][1]["semantics"]
    assert "ltlsplitter_edited" not in r2_saved


def test_save_session_adds_new_requirements_and_variables_and_drops_deleted_ones(tmp_path):
    source = _write_source(tmp_path)
    fret_import = import_fret_file(source)
    fret_import.requirements = [r for r in fret_import.requirements if r.reqid != "r2"]
    fret_import.requirements.append(FretRequirement(
        reqid="new1", fulltext="speed stays low", pt_formula="(H (speed < 5))", ft_formula="(G (speed < 5))",
        variable_names=["speed"],
    ))
    fret_import.variables.append(Variable(name="speed", type=VariableType.FLOAT, role=VariableRole.INPUT,
                                          topic="/odom/speed", min_value=0.0, max_value=10.0))
    fret_import.variables.append(Variable(name="mode", type=VariableType.ENUM, enum_values=["idle", "run"]))
    fret_import.variables.append(Variable(name="near", type=VariableType.BOOL, role=VariableRole.INTERNAL,
                                          assignment="speed < 1", copilot_assignment="speed < constant 1"))
    output = tmp_path / "copy.json"

    save_session(fret_import, output, source_path=source)
    reimported = import_fret_file(output)

    assert [r.reqid for r in reimported.requirements] == ["r1", "new1"]
    assert reimported.requirement("new1").pt_formula == "(H (speed < 5))"
    speed = next(v for v in reimported.variables if v.name == "speed")
    assert (speed.type, speed.topic, speed.min_value, speed.max_value) == (VariableType.FLOAT, "/odom/speed", 0.0, 10.0)
    mode = next(v for v in reimported.variables if v.name == "mode")
    assert mode.enum_values == ["idle", "run"]
    near = next(v for v in reimported.variables if v.name == "near")
    assert (near.role, near.assignment, near.copilot_assignment) == (
        VariableRole.INTERNAL, "speed < 1", "speed < constant 1")


def test_save_session_works_without_a_json_source(tmp_path):
    """An .smv import (or a project started from scratch) has no FRET JSON to start from."""
    fret_import = FretImport(
        project="demo",
        requirements=[FretRequirement(reqid="r1", fulltext="", pt_formula="(H a)", ft_formula="", variable_names=["a"])],
        variables=[Variable(name="a", type=VariableType.BOOL)],
    )
    output = tmp_path / "copy.json"

    save_session(fret_import, output, source_path=tmp_path / "model.smv")

    assert import_fret_file(output).requirement("r1").pt_formula == "(H a)"


def test_untyped_variables_get_their_type_from_how_the_formulas_use_them(tmp_path):
    """FRET leaves dataType empty for unmapped variables (every variable in the real UseCase6
    export). Defaulting those to integer made nuXmv reject "! x" and Spot/SPIN refuse the
    atoms, so nothing was actually checked."""
    source = tmp_path / "untyped.json"
    source.write_text(json.dumps({
        "requirements": [{"reqid": "r1", "fulltext": "", "semantics": {
            "pt": "(H ((u & (speed > 3)) -> ((! d) | (kias <= 70.5))))",
            "ft": "(G ((u & (speed > 3)) -> ((! d) | (kias <= 70.5))))"}}],
        "variables": [{"variable_name": n, "dataType": "", "idType": ""} for n in ("u", "d", "speed", "kias", "unused")],
    }))

    types = {v.name: v.type for v in import_fret_file(source).variables}

    assert types == {"u": VariableType.BOOL, "d": VariableType.BOOL, "speed": VariableType.INT,
                     "kias": VariableType.FLOAT, "unused": VariableType.BOOL}


def test_type_inference_is_not_fooled_by_biconditionals_and_implications():
    from ltlsplitter.core.fret_import import infer_variable_type

    formulas = ["(G ((a <-> b) -> c))", "(H (b <-> a))"]
    assert {infer_variable_type(n, formulas) for n in "abc"} == {VariableType.BOOL}
