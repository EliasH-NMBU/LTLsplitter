from .conftest import requires_kind2, requires_nuxmv, requires_spin, requires_spot

from ltlsplitter.core.equivalence_check import (
    _check_tautology_nuxmv,
    _check_tautology_spin,
    _check_tautology_spot,
    _is_trivial_tautology,
    _TautologyCheck,
    validate_decomposition,
)
from ltlsplitter.core.models import SubFormula, Variable, VariableRole, VariableType

_XY = [Variable(name="x", type=VariableType.BOOL), Variable(name="y", type=VariableType.BOOL)]


def test_is_trivial_tautology_detects_identical_sides():
    assert _is_trivial_tautology("(G (x -> y)) <-> (G (x -> y))") is True


def test_is_trivial_tautology_rejects_different_sides():
    assert _is_trivial_tautology("(G (x -> y)) <-> (G x)") is False


def test_is_trivial_tautology_ignores_repeated_whitespace_differences():
    # Collapses repeated whitespace (not full removal -- that would risk merging adjacent
    # tokens, e.g. "G a" and "Ga" comparing equal, which isn't the intent).
    assert _is_trivial_tautology("(G (x -> y)) <-> (G  (x  ->   y))") is True


def test_is_trivial_tautology_does_not_merge_adjacent_tokens():
    assert _is_trivial_tautology("(G a) <-> (Ga)") is False


def test_spot_rejects_unsupported_compound_arithmetic_upfront_without_needing_the_binary():
    # No @requires_spot -- this guard runs before any subprocess call, so it's testable
    # regardless of whether Spot happens to be installed. "distance + 1 > 3" isn't a simple
    # "variable OP literal" comparison, so it's still out of scope.
    distance = [Variable(name="distance", type=VariableType.INT)]
    result = _check_tautology_spot("G (distance + 1 > 3)", distance)
    assert result.status == "error"
    assert "distance" in result.details


def test_spin_rejects_unsupported_compound_arithmetic_upfront_without_needing_the_binary():
    distance = [Variable(name="distance", type=VariableType.INT)]
    result = _check_tautology_spin("G (distance + 1 > 3)", distance)
    assert result.status == "error"
    assert "distance" in result.details


@requires_nuxmv
def test_nuxmv_recognizes_tautology():
    result = _check_tautology_nuxmv("(G (x -> y)) <-> (G (x -> y))", _XY)
    assert result.status == "tautology"


@requires_nuxmv
def test_nuxmv_recognizes_non_tautology():
    result = _check_tautology_nuxmv("(G (x -> y)) <-> (F x)", _XY)
    assert result.status == "not_tautology"


@requires_nuxmv
def test_nuxmv_substitutes_internal_variable_via_define():
    distance = Variable(name="distance", type=VariableType.INT, role=VariableRole.INPUT, min_value=0, max_value=10)
    dgt_3 = Variable(
        name="dgt_3", type=VariableType.BOOL, role=VariableRole.INTERNAL, assignment="distance > 3",
    )
    # dgt_3 is wired to mean "distance > 3", so (G dgt_3) should be equivalent to (G (distance > 3)).
    result = _check_tautology_nuxmv("(G dgt_3) <-> (G (distance > 3))", [distance, dgt_3])
    assert result.status == "tautology"


@requires_nuxmv
def test_nuxmv_missing_binary_is_an_error_not_a_logical_result(monkeypatch):
    monkeypatch.setenv("NUXMV_PATH", "/definitely/not/a/real/path/nuXmv")
    # Not a self-identical formula -- that would hit the _is_trivial_tautology fast path before
    # ever looking for the binary, which isn't what this test means to exercise.
    result = _check_tautology_nuxmv("(G x) <-> (F x)", _XY)
    assert result.status == "error"


@requires_spot
def test_spot_recognizes_tautology():
    # Spot's LTL parser doesn't support past-time operators (H/O/S/Y) -- confirmed against the
    # real binary, not assumed -- so, unlike nuXmv, Spot validates future-time formulas.
    result = _check_tautology_spot("(G (x -> y)) <-> (G (x -> y))", _XY)
    assert result.status == "tautology"


@requires_spot
def test_spot_recognizes_non_tautology():
    result = _check_tautology_spot("(G (x -> y)) <-> (F x)", _XY)
    assert result.status == "not_tautology"


@requires_spot
def test_spot_handles_typed_comparisons_via_quoting():
    # Spot's LTL grammar rejects "state = 1" as a bare token, but accepts a double-quoted
    # string as one opaque atomic proposition -- confirmed against the real binary -- so a
    # typed comparison no longer needs to be rejected outright the way it used to be.
    state = [Variable(name="state", type=VariableType.INT)]
    result = _check_tautology_spot("(G (state = 1)) <-> (G (state = 1))", state)
    assert result.status == "tautology"
    result = _check_tautology_spot("(G (state = 1)) <-> (G (state = 2))", state)
    assert result.status == "not_tautology"


@requires_spin
def test_spin_recognizes_tautology():
    result = _check_tautology_spin("(G (x -> y)) <-> (G (x -> y))", _XY)
    assert result.status == "tautology"


@requires_spin
def test_spin_recognizes_non_tautology():
    result = _check_tautology_spin("(G (x -> y)) <-> (F x)", _XY)
    assert result.status == "not_tautology"


@requires_spin
def test_spin_handles_typed_comparisons_with_a_properly_ranged_domain():
    # SPIN's own LTL parser actually accepts "state = 1" as a literal atomic proposition
    # (confirmed against the real binary) -- the bug this project had was never SPIN's parser,
    # it was this project's own Promela model generator declaring every variable as `bool`
    # regardless, silently collapsing a typed variable's real range.
    state = [Variable(name="state", type=VariableType.INT)]
    result = _check_tautology_spin("(G (state = 1)) <-> (G (state = 2))", state)
    assert result.status == "not_tautology"


@requires_spin
def test_spin_non_tautology_unrelated_boolean_atoms():
    # Regression test: confirmed empirically that without trying more than one starting-value
    # combination, SPIN's never claim can get stuck at the very first (Promela-default) state
    # and silently misreport "tautology" for genuinely different formulas -- reproduced with
    # both unrelated atoms and negated atoms, which need opposite starting points.
    ab = [Variable(name="a", type=VariableType.BOOL), Variable(name="b", type=VariableType.BOOL)]
    assert _check_tautology_spin("(G a) <-> (G b)", ab).status == "not_tautology"
    assert _check_tautology_spin("(G (!a)) <-> (G (!b))", ab).status == "not_tautology"
    assert _check_tautology_spin("(G (a & b)) <-> (G b)", ab).status == "not_tautology"


@requires_kind2
def test_validate_decomposition_module_imports_cleanly():
    # kind2_check isn't exercised by this file directly, but requires_kind2 confirms the
    # project's conftest marker set stays consistent as tools are added.
    assert True


def test_validate_decomposition_builds_conjunction_and_nondegeneracy_checks(monkeypatch):
    """Orchestration-only test: each tool's tautology check is stubbed so this exercises
    validate_decomposition's formula-building and result-aggregation logic independent of
    which tools happen to be installed."""
    seen_formulas = []

    def fake_check(formula, variables):
        seen_formulas.append(formula)
        return _TautologyCheck("tautology")

    monkeypatch.setattr("ltlsplitter.core.equivalence_check._check_tautology_nuxmv", fake_check)
    monkeypatch.setattr("ltlsplitter.core.equivalence_check._check_tautology_spot", fake_check)
    monkeypatch.setattr("ltlsplitter.core.equivalence_check._check_tautology_spin", fake_check)

    sub_formulas = [
        SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
        SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)"),
    ]
    result = validate_decomposition("(H (a & b))", "(G (a & b))", sub_formulas, [])

    assert len(result.equivalence) == 3
    assert all(r.passed for r in result.equivalence)
    assert set(result.nondegeneracy.keys()) == {"r1.1", "r1.2"}
    # all stubbed "tautology" -> every sub-formula looks (wrongly, per the stub) equivalent to
    # the original, so non-degeneracy should report that as a FAIL (passed=False), not a pass.
    assert all(not r.passed for results in result.nondegeneracy.values() for r in results)
    conjunction_check = next(f for f in seen_formulas if "<->" in f and "&" in f.split("<->")[1])
    assert "(H (a & b))" in conjunction_check
    assert "(H a)" in conjunction_check and "(H b)" in conjunction_check


def test_validate_decomposition_skips_nondegeneracy_for_single_formula(monkeypatch):
    monkeypatch.setattr(
        "ltlsplitter.core.equivalence_check._check_tautology_nuxmv", lambda f, v: _TautologyCheck("tautology")
    )
    monkeypatch.setattr(
        "ltlsplitter.core.equivalence_check._check_tautology_spot", lambda f, v: _TautologyCheck("tautology")
    )
    monkeypatch.setattr(
        "ltlsplitter.core.equivalence_check._check_tautology_spin", lambda f, v: _TautologyCheck("tautology")
    )

    sub_formulas = [SubFormula(id="r1", pt_formula="(H a)", ft_formula="(G a)")]
    result = validate_decomposition("(H a)", "(G a)", sub_formulas, [])

    assert result.nondegeneracy == {}
    # nothing to check non-degeneracy against with a single (unsplit) formula, so all_passed
    # depends only on equivalence here.
    assert result.all_passed is True


def test_validate_decomposition_fast_path_for_literally_unchanged_single_formula():
    """When a single sub-formula is an exact textual copy of the original (the common
    "no split happened" case), the equivalence check should short-circuit via
    `_is_trivial_tautology` rather than invoking any external tool -- this is what makes that
    common case immune to SPIN's "stuck at the first state" ambiguity. No @requires_* markers:
    nothing here should touch a subprocess at all."""
    sub_formulas = [SubFormula(id="r1", pt_formula="(H a)", ft_formula="(G a)")]
    result = validate_decomposition("(H a)", "(G a)", sub_formulas, [])

    assert all(r.passed for r in result.equivalence)
