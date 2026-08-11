from pathlib import Path

from .conftest import requires_ogma

from ltlsplitter.core.models import Specification, Variable, VariableType
from ltlsplitter.core.ogma import ToolNotFoundError, _find_ogma, generate_ros2_monitor


def test_find_ogma_raises_when_ogma_path_points_nowhere(monkeypatch):
    monkeypatch.setenv("OGMA_PATH", "/definitely/not/a/real/path/ogma")
    try:
        _find_ogma()
        raise AssertionError("expected ToolNotFoundError")
    except ToolNotFoundError:
        pass


def test_generate_with_no_formula_raises_value_error():
    spec = Specification(requirement_id="r1")
    try:
        generate_ros2_monitor(spec, Path("/tmp/unused"))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


@requires_ogma
def test_generate_single_operator_formula_succeeds(tmp_path):
    variables = [
        Variable(name="request", type=VariableType.BOOL, ros_node="/n"),
        Variable(name="grant", type=VariableType.BOOL, ros_node="/n"),
    ]
    spec = Specification(requirement_id="r1.1", ltl_formula="H (request -> grant)")

    result = generate_ros2_monitor(spec, tmp_path, variables)

    assert result == tmp_path
    copilot_hs = (tmp_path / "copilot" / "src" / "Copilot.hs").read_text()
    assert "request :: Stream (Bool)" in copilot_hs
    assert "grant :: Stream (Bool)" in copilot_hs
    assert "handlerR1_1" in copilot_hs


@requires_ogma
def test_generate_nested_temporal_operators_raises_clear_error(tmp_path):
    variables = [
        Variable(name="request", type=VariableType.BOOL, ros_node="/n"),
        Variable(name="grant", type=VariableType.BOOL, ros_node="/n"),
    ]
    spec = Specification(requirement_id="r1.2", ltl_formula="G (request -> F grant)")

    try:
        generate_ros2_monitor(spec, tmp_path, variables)
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "nest" in str(exc).lower() or "temporal operator" in str(exc).lower()


@requires_ogma
def test_generate_typed_variables_use_correct_copilot_and_c_types(tmp_path):
    variables = [Variable(name="count", type=VariableType.INT, ros_node="/n")]
    spec = Specification(requirement_id="r2", ltl_formula="H (count)")

    generate_ros2_monitor(spec, tmp_path, variables)

    copilot_hs = (tmp_path / "copilot" / "src" / "Copilot.hs").read_text()
    assert "count :: Stream (Int32)" in copilot_hs
