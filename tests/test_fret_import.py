import json
from pathlib import Path

import pytest

from ltlsplitter.core.fret_import import (
    InvalidFretFileError,
    _normalize_type_field,
    append_sub_formulas_and_save,
    import_fret_file,
)
from ltlsplitter.core.models import FretRequirement, SubFormula, VariableRole, VariableType

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


def test_append_sub_formulas_and_save_round_trips_is_assumption(tmp_path):
    """A user-toggled is_assumption (on an existing, already-imported requirement) must survive
    a split-save -- otherwise the checkbox toggle introduced for the assume/guarantee fix would
    silently appear to work in the GUI, then evaporate the moment a split is saved."""
    source = tmp_path / "source.json"
    source.write_text(json.dumps({
        "requirements": [
            {"reqid": "r1", "parent_reqid": "", "project": "demo", "fulltext": "...",
             "semantics": {"pt": "(H a)", "ft": "(G a)", "variables": ["a"]}},
        ],
        "variables": [{"variable_name": "a", "dataType": "boolean", "idType": "Input"}],
    }))
    output = tmp_path / "copy.json"

    # Simulate the user having flipped r1's checkbox to "assumption" before saving the split --
    # `parent` and `current_requirements` share the same object, as they would in the real GUI
    # flow (both read off `self.state.fret_import.requirements`).
    parent = FretRequirement(reqid="r1", fulltext="...", pt_formula="(H a)", ft_formula="(G a)", is_assumption=True)
    sub_formulas = [SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)")]
    current_requirements = [parent]

    append_sub_formulas_and_save(source, sub_formulas, parent, "demo", {"a"}, output, current_requirements=current_requirements)
    reimported = import_fret_file(output)

    assert reimported.requirement("r1").is_assumption is True
    # The sub-formula inherits the parent's (now-toggled) is_assumption value.
    assert reimported.requirement("r1.1").is_assumption is True
