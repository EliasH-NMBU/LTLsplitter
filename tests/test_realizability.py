from .conftest import requires_nuxmv, requires_strix

from ltlsplitter.core.models import Specification, Variable, VariableType
from ltlsplitter.core.realizability import ToolNotFoundError, _find_binary, check_consistency, check_realizability


def test_find_binary_raises_when_not_found():
    try:
        _find_binary("SOME_MADE_UP_TOOL_PATH", "definitely-not-a-real-binary")
        raise AssertionError("expected ToolNotFoundError")
    except ToolNotFoundError:
        pass


def test_check_consistency_with_no_formulas_short_circuits():
    result = check_consistency([])
    assert result.consistent is True


def test_check_realizability_with_no_formula_short_circuits():
    result = check_realizability(Specification(requirement_id="r1"), [], [])
    assert result.realizable is False


@requires_nuxmv
def test_check_consistency_detects_conflict():
    specs = [
        Specification(requirement_id="r1", ltl_formula="G x"),
        Specification(requirement_id="r2", ltl_formula="G !x"),
    ]
    variables = [Variable(name="x", type=VariableType.BOOL, ros_node="/n")]

    result = check_consistency(specs, variables)

    assert result.consistent is False
    assert set(result.conflicting_requirement_ids) == {"r1", "r2"}


@requires_nuxmv
def test_check_consistency_passes_for_compatible_specs():
    specs = [
        Specification(requirement_id="r1", ltl_formula="G (x -> F y)"),
        Specification(requirement_id="r2", ltl_formula="F x"),
    ]
    variables = [
        Variable(name="x", type=VariableType.BOOL, ros_node="/n"),
        Variable(name="y", type=VariableType.BOOL, ros_node="/n"),
    ]

    result = check_consistency(specs, variables)

    assert result.consistent is True


@requires_nuxmv
def test_check_consistency_isolates_conflict_from_unrelated_requirement():
    specs = [
        Specification(requirement_id="r1", ltl_formula="G x"),
        Specification(requirement_id="r2", ltl_formula="G !x"),
        Specification(requirement_id="r3", ltl_formula="F y"),
    ]
    variables = [
        Variable(name="x", type=VariableType.BOOL, ros_node="/n"),
        Variable(name="y", type=VariableType.BOOL, ros_node="/n"),
    ]

    result = check_consistency(specs, variables)

    assert result.consistent is False
    assert set(result.conflicting_requirement_ids) == {"r1", "r2"}


@requires_strix
def test_check_realizability_true_for_realizable_spec():
    spec = Specification(requirement_id="r1", ltl_formula="G (request -> F grant)")

    result = check_realizability(spec, ["request"], ["grant"])

    assert result.realizable is True


@requires_strix
def test_check_realizability_false_when_system_must_predict_future_input():
    spec = Specification(requirement_id="r1", ltl_formula="G (grant <-> (X request))")

    result = check_realizability(spec, ["request"], ["grant"])

    assert result.realizable is False
