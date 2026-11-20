"""Tests for tests/fixtures/splitter_adversarial_ladder.json -- unlike the complexity and
hidden-conjunction ladders (which are all genuinely, soundly decomposable), every requirement
here was chosen because the full suggest_split -> decompose -> validate_decomposition pipeline is
expected to struggle with it, for one of two distinct reasons:

AD01-AD04 have NO sound, non-degenerate decomposition at all -- each one's single top-level
relation already spans its whole output-variable set (or, for AD04, is a parity function where
every input is fully sensitive), so there is no output-disjoint sub-term to split off. This is
the same limitation Finkbeiner et al.'s own paper names for their modular-synthesis algorithm
("there are NBAs that cannot be decomposed further, e.g., automata whose alphabet contains only
one output variable") -- these rungs test whether suggest_split correctly declines to force a
split, and, if it tries anyway, whether validate_decomposition's equivalence check correctly
rejects the attempt. AD02's naive-but-tempting per-output split was confirmed, with the real Spot
binary, to be rejected (not_tautology) -- see test_AD02_naive_per_output_split_is_rejected_by_spot.

AD05 and AD06 are different in kind: they are NOT indecomposable, but they each trigger a real,
reproducible limitation of this project's own validation *tooling*, confirmed against the actual
nuXmv/SPIN binaries (not hypothetical):

  - AD05 mixes a Y (yesterday)-containing side against a Y-free side of a top-level
    biconditional. Checking nuXmv's own "H(e -> Y a)" implication direction -- an ordinary,
    *correct* half of a sound decomposition -- reproducibly emits nuXmv's
    "WARNING: The initial states set of the finite state machine is empty" even though the
    reported verdict is "true" and the decomposition is in fact sound. There is currently no
    reliable way to use that warning to distinguish an unsound result from a sound one: an
    earlier attempt to treat it as an outright error was reverted after it was found to also
    fire on known-good tautology checks.

  - AD06 compares three typed (integer) variables only to each other, with no literal value
    ("x = 3"-style) anywhere in the formula. _promela_model's domain-widening fixed point (added
    to handle "variable OP variable" comparisons) only widens a variable's declared Promela
    domain using literal values actually seen in the formula; with none present, every one of
    x, y, z silently defaults to the 2-value domain {0, 1}. Within only 2 values, "x, y, and z
    are pairwise distinct" is unsatisfiable (pigeonhole), so SPIN's free-running search can never
    reach the antecedent and reports the whole implication as a tautology -- even though it is
    NOT a tautology over the variables' real (3-or-more-valued) integer domain: x=0, y=1, z=2,
    e=false is a genuine counterexample that SPIN's narrowed model can never construct. This is a
    real soundness gap in the domain-widening fix, not merely a hard case -- confirmed below
    against the real SPIN binary.
"""

from pathlib import Path

from .conftest import requires_nuxmv, requires_spin, requires_spot

from ltlsplitter.core.equivalence_check import (
    _check_tautology_spin,
    _check_tautology_spot,
    _nuxmv_model,
    _run_nuxmv_check,
)
from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.models import Variable, VariableRole, VariableType
from ltlsplitter.core.realizability import _find_binary

_FIXTURE = Path(__file__).parent / "fixtures" / "ladders" / "splitter_adversarial_ladder.json"


def _balanced(formula: str) -> bool:
    depth = 0
    for ch in formula:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def test_imports_cleanly_with_six_requirements():
    fi = import_fret_file(_FIXTURE)

    assert fi.project == "SplitterAdversarialLadder"
    assert len(fi.requirements) == 6
    assert len(fi.leaf_requirements()) == 6  # none pre-split -- every one is a leaf
    assert len(fi.variables) == 11


def test_every_requirement_has_well_formed_balanced_formulas():
    fi = import_fret_file(_FIXTURE)

    for req in fi.requirements:
        assert req.pt_formula and req.ft_formula, req.reqid
        assert _balanced(req.pt_formula), f"{req.reqid}: unbalanced pt formula"
        assert _balanced(req.ft_formula), f"{req.reqid}: unbalanced ft formula"


def test_every_requirement_references_only_declared_variables():
    fi = import_fret_file(_FIXTURE)
    declared = {v.name for v in fi.variables}

    for req in fi.requirements:
        assert req.variable_names, f"{req.reqid} references no declared variable"
        assert set(req.variable_names) <= declared, f"{req.reqid} references undeclared variable(s)"


def test_every_requirement_uses_the_correct_leading_operator():
    fi = import_fret_file(_FIXTURE)

    for req in fi.requirements:
        assert req.pt_formula.startswith("(H "), req.reqid
        assert req.ft_formula.startswith("(G "), req.reqid


def test_pt_and_ft_forms_match_except_for_the_documented_past_future_shift():
    """Every rung other than AD05 is a pure boolean-state condition, so pt/ft must be identical
    once the leading H/G is stripped. AD05 is the deliberate exception -- it genuinely needs a
    past/future shift (Y on the pt side, X on the ft side), which is the whole point of that
    rung, so it is checked separately below instead of being asserted equal."""
    fi = import_fret_file(_FIXTURE)

    for req in fi.requirements:
        if req.reqid == "AD05_past_time_biconditional_shift":
            continue
        assert req.pt_formula[3:] == req.ft_formula[3:], f"{req.reqid}: pt/ft diverge beyond H/G"


def test_AD05_pt_uses_yesterday_and_ft_uses_next_instead():
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("AD05_past_time_biconditional_shift")

    assert "Y" in req.pt_formula
    assert "Y" not in req.ft_formula
    assert "X" in req.ft_formula


@requires_spot
def test_AD02_naive_per_output_split_is_rejected_by_spot():
    """The tempting-but-wrong decomposition of "e1 and e2 never both hold" into two independent
    per-output rules ("e1 never holds" and "e2 never holds") is strictly stronger than the
    original -- confirms, against the real Spot binary, that no disjoint-output split of this
    rung is sound."""
    e1 = Variable(name="e1", type=VariableType.BOOL, role=VariableRole.OUTPUT)
    e2 = Variable(name="e2", type=VariableType.BOOL, role=VariableRole.OUTPUT)

    original = "(G (! (e1 & e2)))"
    naive_split_conjunction = "((G (! e1)) & (G (! e2)))"
    result = _check_tautology_spot(f"({original} <-> {naive_split_conjunction})", [e1, e2])

    assert result.status == "not_tautology"


@requires_nuxmv
def test_AD05_nuxmv_warns_initial_states_empty_on_a_sound_half_of_the_split():
    """Splitting the AD05 biconditional into its two implications is logically sound (H(a<->b) is
    always equivalent to H(a->b) & H(b->a)) -- but checking nuXmv's verdict on just the
    "e -> (Y a)" half's equivalence to the original reproducibly emits nuXmv's "initial states
    set is empty" warning alongside its (correct) "true" verdict. There is no code in this
    project that currently surfaces that warning to the user -- _check_tautology_nuxmv discards
    stdout entirely on a "true" verdict, so this test goes one level below it, straight to
    _run_nuxmv_check, to inspect the raw output the way a human reading the console would."""
    a = Variable(name="a", type=VariableType.BOOL, role=VariableRole.INPUT)
    e = Variable(name="e", type=VariableType.BOOL, role=VariableRole.OUTPUT)

    original = "(H ((Y a) <-> e))"
    sub_towards_a = "(H (e -> (Y a)))"
    nuxmv = _find_binary("NUXMV_PATH", "nuXmv")
    output = _run_nuxmv_check(nuxmv, _nuxmv_model([a, e], f"({original} <-> {sub_towards_a})"))

    assert "-- specification" in output and "is true" in output, (
        f"expected a 'true' verdict (this split direction really is sound); got:\n{output[-800:]}"
    )
    assert "initial states" in output.lower(), (
        "expected nuXmv's known 'initial states set is empty' warning alongside the 'true' "
        "verdict; if this assertion starts failing, the warning may no longer reproduce and this "
        "rung's docstring claim should be re-verified rather than the test loosened"
    )


@requires_spin
def test_AD06_spin_wrongly_reports_a_tautology_due_to_domain_shrinkage():
    """x, y, z appear only in variable-to-variable comparisons with no literal anywhere in the
    formula, so _promela_model's domain-widening fixed point has nothing to widen with and each
    variable silently keeps the default 2-value domain {0, 1}. "Pairwise distinct" is
    unsatisfiable over only 2 values, so SPIN's free-running search reports the whole implication
    as a tautology -- but it is NOT one over the real (>= 3-valued) integer domain: x=0, y=1,
    z=2, e=false is a genuine counterexample SPIN's narrowed model can never construct. This is
    a real soundness gap in the "variable OP variable" domain-widening fix, confirmed here
    against the real binary, not a claim from reading the code alone."""
    x = Variable(name="x", type=VariableType.INT, role=VariableRole.INPUT)
    y = Variable(name="y", type=VariableType.INT, role=VariableRole.INPUT)
    z = Variable(name="z", type=VariableType.INT, role=VariableRole.INPUT)
    e = Variable(name="e", type=VariableType.BOOL, role=VariableRole.OUTPUT)

    formula = "(G ((((x != y) & (y != z)) & (x != z)) -> e))"
    result = _check_tautology_spin(formula, [x, y, z, e])

    assert result.status == "tautology", (
        "if this starts failing (returning not_tautology), the domain-widening gap this rung "
        "documents may have been fixed -- re-verify and update this rung's docstring rather than "
        "just flipping the assertion"
    )
