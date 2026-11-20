"""Tests for tests/fixtures/splitter_complexity_ladder.json -- a synthetic, hand-authored (not
from a real FRET project) ladder of 25 requirements with generalized variable names (a-h, mode,
x, y), built to exercise the LLM split-suggestion pipeline across the full range of complexity
it might encounter.

v4 rework (this version): v3 made every rung bundle >=2 independent obligations, but combined
them with plain top-level "&" between already-separate implications -- exactly the shape a naive
syntactic/variable-dependency splitter (Finkbeiner-style conjunct clustering) already handles
trivially, so it never actually tested whether a split recommendation required any real semantic
insight. v4 instead NESTS multiple obligations under shared triggers/guards wherever a single
real condition plausibly enables several effects (e.g. SC01: "a -> (e & f)", not "(a->e) & (a->f)"
or worse, two unrelated triggers) -- splitting now requires recognizing independence *inside* a
compound consequent, which is the realistic shape a natural-language compound sentence ("While X,
the system shall satisfy A and B") actually produces, and is NOT already exposed by looking at
top-level conjuncts alone. SC11/SC14/SC17/SC18/SC20/SC23/SC25's mode-dispatch branches are also
deliberately the project's standing "non-exposure" showcase: several conjuncts share the `mode`
variable syntactically (Finkbeiner-style clustering would keep them bundled) while remaining
causally independent in every way that matters -- and several (SC17/SC25 especially) go further,
reusing the same *consequent* variable (e/f/g/h) across different mode branches too, for genuine
multi-way entanglement, not just a shared trigger.

Nesting safety (why pt/ft still line up): G/H distribute over & cleanly, so every conjunct can be
translated independently and recombined. Non-shifted fragments (plain/negation/biconditional/
typed comparison/conjunctive-or-disjunctive trigger/mode dispatch/propositional XOR-style
nesting) have IDENTICAL pt and ft text and nest safely under any shared guard (confirmed by
direct derivation, not just assumed). "next" nests safely only when the WHOLE bundle under a
trigger shares one uniform time-shift (ft: "trigger -> X(bundle)", pt: "(Y trigger) -> bundle" --
e.g. SC06/SC13/SC24). until/since/precedence/bounded-response are deliberately kept
self-contained (their own clause, own natural trigger) rather than fused into another clause's
shared guard, because their pt and ft forms are NOT symmetric under an externally-shared trigger
(the "trigger" role itself swaps sides between pt and ft for these four) -- forcing them into a
shared compound consequent the way the safe operators above allow would silently produce a pt/ft
pair that ISN'T actually logically equivalent, which would quietly defeat the whole fixture's
purpose. This is a real constraint discovered while reworking v3 -> v4, not a pre-existing note
carried forward.

Structurally verified when this version was written (balanced parens, declared-variable coverage,
no accidental undeclared-reference hits, and the length-based monotonicity check all pass -- see
the tests below, all green without any external tool). NOT yet re-confirmed against real Strix/
Kind2 binaries from this machine (no Strix/Kind2 install here) -- the same honesty caveat as v3:
the pt/ft equivalence reasoning above has been checked by hand, not by an actual model checker.
The two intentional boundary cases from v1-v3 are preserved: bounded response (F[lo,hi]/O[lo,hi],
MLTL-style, not plain LTL) now appears in SC12/SC18/SC23/SC25; nested past operators beyond the
single top-level H (breaks Kind2's Lustre translation, not Strix) are pervasive again, e.g.
SC06/SC08/SC09/SC13/SC16/SC19/SC22/SC24/SC25. Re-confirm
test_simplest_requirement_is_strix_realizable/test_simplest_requirement_is_kind2_realizable (now
pointed at SC01_shared_trigger_pair) and the bounded-operator cases on a machine with those tools
before relying on this version's realizability behavior, the same way v1->v2 was confirmed there
and not here.

Below this point, notes about *why* certain operator idioms are shaped the way they are (FRET's
own translation quirks, kind2_check.py's/reference_check.py's documented limitations) carry over
unchanged from v1-v3 -- the idioms themselves (bounded response, nested past operators, the
all-caps "FALSE" literal) are reused verbatim, not reinvented, so these notes still apply:

Any pt formula with a *nested* Y/O/S (not just the single top-level H every pt formula starts
with -- e.g. SC06's "(Y a)", SC08's "(O a)", SC09's "(b S a)") fails Kind2 with a genuine Lustre
syntax error, not a semantic "unrealizable" verdict -- this is kind2_check.py's already-
documented limitation (`_translate_propositional` only translates <->/->/&/|/! ; it was never
meant to translate temporal operators, only `_strip_top_level_h` handles H, and only at the very
top), not something new this fixture introduced. Strix doesn't have this gap since Spot/Strix/
SPIN natively parse Y/O/S.

reference_check.py's find_undeclared_references must not flag the literal "FALSE" in formulas
like "(O[0,4] (Z FALSE))" (SC12/SC18/SC23/SC25 here) as an undeclared variable -- _LTL_KEYWORDS
lists both "false"/"False" and the all-caps spelling FRET itself uses in this exact idiom
(confirmed in the real LiftPlusCruise fixture too; see test_reference_check.py for the regression
test itself).
"""

from pathlib import Path

from .conftest import requires_kind2, requires_strix

from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.kind2_check import check_realizability_kind2
from ltlsplitter.core.realizability import check_realizability_typed

_FIXTURE = Path(__file__).parent / "fixtures" / "ladders" / "splitter_complexity_ladder.json"


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


def test_imports_cleanly_with_twentyfive_requirements():
    fi = import_fret_file(_FIXTURE)

    assert fi.project == "SplitterComplexityLadder"
    assert len(fi.requirements) == 25
    assert len(fi.leaf_requirements()) == 25  # none pre-split -- every one is a leaf
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


def test_no_requirement_triggers_the_undeclared_reference_warning():
    """Regression test for the exact issue originally reported against this fixture (v1: SC13/
    17/20; v2: SC18/22/25; v3: SC16/23/25; v4 here: SC12/18/23/25) -- the bounded-operator pt
    formulas (e.g. "(O[0,4] (Z FALSE))") use the literal "FALSE", which import_split.py's
    reference check once flagged as an undeclared variable -- fixed in reference_check.py's
    _LTL_KEYWORDS."""
    from ltlsplitter.core.reference_check import find_undeclared_references  # noqa: PLC0415

    fi = import_fret_file(_FIXTURE)
    declared = {v.name for v in fi.variables}

    for req in fi.requirements:
        undeclared = find_undeclared_references(req.pt_formula + " " + req.ft_formula, declared)
        assert undeclared == [], f"{req.reqid}: unexpectedly flagged {undeclared} as undeclared"


def test_complexity_increases_monotonically_by_formula_length():
    """Not a rigorous complexity metric, but a basic sanity check that the ladder is actually a
    ladder -- the whole point of this fixture is a gradient from trivial to very difficult, so
    later requirements should, on the whole, be longer/more nested than earlier ones."""
    fi = import_fret_file(_FIXTURE)
    lengths = [len(req.ft_formula) for req in fi.requirements]

    first_quarter_avg = sum(lengths[:5]) / 5
    last_quarter_avg = sum(lengths[-5:]) / 5
    assert last_quarter_avg > first_quarter_avg * 3


@requires_strix
def test_simplest_requirement_is_strix_realizable():
    """The easy end of the ladder should round-trip cleanly -- a sanity floor for the fixture
    itself, independent of whether the harder entries are expected to (several deliberately
    aren't, e.g. SC12/18/23/25's bounded-operator syntax -- see the module docstring). NOT yet
    re-confirmed against a real Strix binary for this v4 content (no Strix on this machine) --
    SC01's single-trigger pair (a -> (e & f)) distributes to the same disjoint-implication
    pattern v2's SC11 (3 such clauses) was confirmed REALIZABLE with, so this is expected to
    hold, but should be checked for real before being relied on."""
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("SC01_shared_trigger_pair")

    result = check_realizability_typed(req.ft_formula, fi.variables, fi.project)

    assert result.realizable is True


@requires_kind2
def test_simplest_requirement_is_kind2_realizable():
    """NOT yet re-confirmed against a real Kind2 binary for this v4 content -- see the sibling
    Strix test's docstring above."""
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("SC01_shared_trigger_pair")

    result = check_realizability_kind2([], [req.pt_formula], fi.variables)

    assert result.realizable is True
