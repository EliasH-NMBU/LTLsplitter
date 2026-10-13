from .conftest import requires_kind2

from ltlsplitter.core.kind2_check import _strip_top_level_h, _translate_propositional, check_realizability_kind2
from ltlsplitter.core.models import Variable, VariableRole, VariableType


def test_translate_propositional_handles_iff_before_implication():
    # "<->" contains "->" as a substring -- must not be double-translated or corrupted.
    assert _translate_propositional("a <-> b") == "a = b"
    assert _translate_propositional("a -> b") == "a => b"
    assert _translate_propositional("a & b | !c") == "a  and  b  or   not c"


def test_strip_top_level_h_extracts_body():
    assert _strip_top_level_h("(H ((classifier = 1) -> (state = 1)))") == "(classifier = 1) -> (state = 1)"


def test_strip_top_level_h_returns_none_for_unsupported_shapes():
    assert _strip_top_level_h("G (x -> y)") is None
    assert _strip_top_level_h("(H (a)) & (H (b))") is None


def test_check_with_no_formulas_short_circuits():
    result = check_realizability_kind2([], [], [])
    assert result.realizable is False


def test_check_with_only_unsupported_shapes_reports_clearly():
    result = check_realizability_kind2([], ["G (x -> y)"], [Variable(name="x", type=VariableType.BOOL)])
    assert result.realizable is False
    assert "shape" in result.details.lower()


@requires_kind2
def test_check_realizable_formula():
    classifier = Variable(name="classifier", type=VariableType.INT, role=VariableRole.INPUT)
    state = Variable(name="state", type=VariableType.INT, role=VariableRole.OUTPUT)

    result = check_realizability_kind2([], ["(H ((classifier = 1) -> (state = 1)))"], [classifier, state])

    assert result.realizable is True


@requires_kind2
def test_check_unrealizable_contradictory_formulas():
    state = Variable(name="state", type=VariableType.INT, role=VariableRole.OUTPUT)

    result = check_realizability_kind2([], ["(H (state = 1))", "(H (state = 2))"], [state])

    assert result.realizable is False


@requires_kind2
def test_check_substitutes_internal_variable_via_ghost_assignment():
    distance = Variable(name="distance", type=VariableType.INT, role=VariableRole.INPUT)
    far = Variable(name="far", type=VariableType.BOOL, role=VariableRole.INTERNAL, assignment="distance > 7")
    state = Variable(name="state", type=VariableType.INT, role=VariableRole.OUTPUT)

    result = check_realizability_kind2([], ["(H (far -> (state = 1)))"], [distance, far, state])

    assert result.realizable is True


@requires_kind2
def test_check_treats_assumption_as_environment_constraint_not_guarantee():
    """The whole point of the assume/guarantee split: an assumption that constrains an input
    variable (here, "state" is an input) must not be flat-guaranteed -- that would make the
    system responsible for a variable it doesn't control, an unrealizable-by-construction
    modeling artifact rather than a genuine synthesis failure."""
    state = Variable(name="state", type=VariableType.INT, role=VariableRole.INPUT)
    grant = Variable(name="grant", type=VariableType.BOOL, role=VariableRole.OUTPUT)

    result = check_realizability_kind2(
        ["(H (state = 1))"], ["(H ((state = 1) -> grant))"], [state, grant],
    )

    assert result.realizable is True


def test_build_lustre_contract_emits_assume_for_assumptions_and_guarantee_for_guarantees():
    from ltlsplitter.core.kind2_check import _build_lustre_contract

    state = Variable(name="state", type=VariableType.INT, role=VariableRole.INPUT)
    lustre, translated_count, skipped = _build_lustre_contract(
        ["(H (state = 1))"], ["(H (state = 2))"], [state],
    )

    assert translated_count == 2
    assert skipped == []
    assert "assume _ha0;" in lustre
    assert "guarantee _hg0;" in lustre
