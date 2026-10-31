from .conftest import requires_nuxmv, requires_strix

from ltlsplitter.core.models import Specification, Variable, VariableRole, VariableType
from ltlsplitter.core.realizability import (
    ToolNotFoundError,
    _find_binary,
    check_consistency,
    check_realizability,
    check_realizability_typed,
)


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
    variables = [Variable(name="x", type=VariableType.BOOL, topic="/n")]

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
        Variable(name="x", type=VariableType.BOOL, topic="/n"),
        Variable(name="y", type=VariableType.BOOL, topic="/n"),
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
        Variable(name="x", type=VariableType.BOOL, topic="/n"),
        Variable(name="y", type=VariableType.BOOL, topic="/n"),
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


def test_check_realizability_typed_rejects_unsupported_compound_arithmetic_upfront_without_needing_the_binary():
    distance = [Variable(name="distance", type=VariableType.INT, role=VariableRole.INPUT)]
    result = check_realizability_typed("G (distance + 1 > 3)", distance, "r1")
    assert result.realizable is False
    assert "distance" in result.details


@requires_strix
def test_check_realizability_typed_handles_typed_comparisons_via_fresh_names():
    # Strix's LTL grammar rejects "classifier = 1" as a bare token and crashes outright on a
    # quoted atomic proposition (unlike Spot) -- confirmed against the real binary -- so this
    # needs fresh-name substitution, not quoting. A system that can freely set "state" to
    # satisfy "state = 1" whenever asked should be realizable.
    variables = [
        Variable(name="classifier", type=VariableType.INT, role=VariableRole.INPUT),
        Variable(name="state", type=VariableType.INT, role=VariableRole.OUTPUT),
    ]
    result = check_realizability_typed("G ((classifier = 1) -> (state = 1))", variables, "r1")
    assert result.realizable is True


@requires_strix
def test_check_realizability_typed_flags_not_realizable_results_as_a_possible_abstraction_artifact():
    # The fresh-name substitution drops real relationships between typed comparisons (e.g.
    # mutual exclusivity between "classifier = 0"/"= 1"/"= 2") -- confirmed by hand that adding
    # such a constraint back can flip a real NOT REALIZABLE verdict to REALIZABLE, so a NOT
    # REALIZABLE result needs this caveat rather than being presented as a bare, final verdict.
    classifier = [Variable(name="classifier", type=VariableType.INT, role=VariableRole.INPUT)]
    result = check_realizability_typed("G ((classifier = 1) & (! (classifier = 1)))", classifier, "r1")
    assert result.realizable is False
    assert "abstracting typed comparisons" in result.details
    assert "Kind2" in result.details


@requires_strix
def test_check_realizability_typed_flags_the_caveat_for_bare_internal_variable_references_too():
    # Regression test: a requirement can reference an Internal variable directly (e.g. "far"),
    # with no "variable OP literal" text anywhere in the formula -- the caveat above only fired
    # for the latter, missing this case even though it carries the exact same risk. Confirmed by
    # hand: two Internal variables that are logical complements of the same base variable
    # ("far := distance > 7", "near := distance <= 7") produce a spurious NOT REALIZABLE verdict,
    # since Strix's environment gets to pick them independently -- a combination that can't
    # actually happen.
    distance = Variable(name="distance", type=VariableType.INT, role=VariableRole.INPUT)
    far = Variable(name="far", type=VariableType.BOOL, role=VariableRole.INTERNAL, assignment="distance > 7")
    near = Variable(name="near", type=VariableType.BOOL, role=VariableRole.INTERNAL, assignment="distance <= 7")
    alarm = Variable(name="alarm", type=VariableType.BOOL, role=VariableRole.OUTPUT)

    result = check_realizability_typed(
        "(G ((far -> alarm) & (near -> (! alarm))))", [distance, far, near, alarm], "r1",
    )

    assert result.realizable is False
    assert "Internal (derived) variables" in result.details
    assert "Kind2" in result.details


@requires_strix
def test_check_realizability_typed_does_not_add_the_caveat_for_purely_boolean_formulas():
    # No typed comparisons were abstracted here -- Strix sees exactly the formula as written,
    # so a NOT REALIZABLE verdict is not an abstraction artifact and shouldn't be captioned as one.
    variables = [
        Variable(name="request", type=VariableType.BOOL, role=VariableRole.INPUT),
        Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT),
    ]
    result = check_realizability_typed("G (grant <-> (X request))", variables, "r1")
    assert result.realizable is False
    assert "abstracting typed comparisons" not in result.details


@requires_strix
def test_check_realizability_typed_buckets_internal_variables_as_inputs():
    variables = [
        Variable(name="distance", type=VariableType.INT, role=VariableRole.INPUT),
        Variable(name="far", type=VariableType.BOOL, role=VariableRole.INTERNAL, assignment="distance > 7"),
        Variable(name="state", type=VariableType.BOOL, role=VariableRole.OUTPUT),
    ]
    # "far" is a bare Internal identifier (not a comparison) -- without bucketing it into
    # Strix's --ins, this would fail as an unclassified atomic proposition.
    result = check_realizability_typed("G (far -> state)", variables, "r1")
    assert result.realizable is True
