from pathlib import Path

import pytest

from ltlsplitter.core.fret_import import InvalidFretFileError, import_fret_file
from ltlsplitter.core.models import VariableRole, VariableType

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
