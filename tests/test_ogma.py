from pathlib import Path

from .conftest import requires_ogma

from ltlsplitter.core.models import Specification, Variable, VariableRole, VariableType
from ltlsplitter.core.ogma import ToolNotFoundError, _find_ogma, generate_ros2_monitor


def test_find_ogma_raises_when_ogma_path_points_nowhere(monkeypatch):
    monkeypatch.setenv("OGMA_PATH", "/definitely/not/a/real/path/ogma")
    try:
        _find_ogma()
        raise AssertionError("expected ToolNotFoundError")
    except ToolNotFoundError:
        pass


def test_generate_with_no_formula_raises_value_error():
    specs = [Specification(requirement_id="r1")]
    try:
        generate_ros2_monitor(specs, Path("/tmp/unused"))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


@requires_ogma
def test_generate_single_operator_formula_succeeds(tmp_path):
    variables = [
        Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
        Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
    ]
    specs = [Specification(requirement_id="r1.1", ltl_formula="H (request -> grant)")]

    result = generate_ros2_monitor(specs, tmp_path, variables)

    assert result == tmp_path
    copilot_hs = (tmp_path / "copilot" / "src" / "Copilot.hs").read_text()
    assert "request :: Stream (Bool)" in copilot_hs
    assert "grant :: Stream (Bool)" in copilot_hs
    assert "handlerR1_1" in copilot_hs


@requires_ogma
def test_generate_multiple_specs_emits_one_property_each(tmp_path):
    variables = [
        Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
        Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
    ]
    specs = [
        Specification(requirement_id="r1.1", ltl_formula="H (request)"),
        Specification(requirement_id="r1.2", ltl_formula="H (grant)"),
    ]

    generate_ros2_monitor(specs, tmp_path, variables)

    copilot_hs = (tmp_path / "copilot" / "src" / "Copilot.hs").read_text()
    assert "handlerR1_1" in copilot_hs
    assert "handlerR1_2" in copilot_hs


@requires_ogma
def test_generate_nested_temporal_operators_raises_clear_error(tmp_path):
    variables = [
        Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
        Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
    ]
    specs = [Specification(requirement_id="r1.2", ltl_formula="G (request -> F grant)")]

    try:
        generate_ros2_monitor(specs, tmp_path, variables)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "nest" in str(exc).lower() or "temporal operator" in str(exc).lower()


@requires_ogma
def test_generate_typed_variables_use_correct_copilot_and_c_types(tmp_path):
    variables = [Variable(name="count", type=VariableType.INT, role=VariableRole.OUTPUT)]
    specs = [Specification(requirement_id="r2", ltl_formula="H (count)")]

    generate_ros2_monitor(specs, tmp_path, variables)

    copilot_hs = (tmp_path / "copilot" / "src" / "Copilot.hs").read_text()
    assert "count :: Stream (Int32)" in copilot_hs


@requires_ogma
def test_generate_internal_variable_is_derived_not_subscribed(tmp_path):
    variables = [
        Variable(name="distance_to_target", type=VariableType.INT, role=VariableRole.INPUT),
        Variable(
            name="dgt_3", type=VariableType.BOOL, role=VariableRole.INTERNAL,
            assignment="distance_to_target > 3", copilot_assignment="distance_to_target > constant 3",
        ),
    ]
    specs = [Specification(requirement_id="r3", ltl_formula="H (dgt_3)")]

    generate_ros2_monitor(specs, tmp_path, variables)

    copilot_hs = (tmp_path / "copilot" / "src" / "Copilot.hs").read_text()
    assert "distance_to_target > constant 3" in copilot_hs
