from .conftest import requires_nuxmv, requires_spin, requires_spot

from ltlsplitter.core.equivalence_check import (
    _check_tautology_nuxmv,
    _check_tautology_spin,
    _check_tautology_spot,
    _TautologyCheck,
    validate_decomposition,
)
from ltlsplitter.core.models import SubFormula, Variable, VariableRole, VariableType

_XY = [Variable(name="x", type=VariableType.BOOL), Variable(name="y", type=VariableType.BOOL)]


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
    result = _check_tautology_nuxmv("(G x) <-> (G x)", _XY)
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


@requires_spin
def test_spin_recognizes_tautology():
    result = _check_tautology_spin("(G (x -> y)) <-> (G (x -> y))", _XY)
    assert result.status == "tautology"


@requires_spin
def test_spin_recognizes_non_tautology():
    result = _check_tautology_spin("(G (x -> y)) <-> (F x)", _XY)
    assert result.status == "not_tautology"


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
