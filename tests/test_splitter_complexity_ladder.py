"""Tests for tests/fixtures/splitter_complexity_ladder.json -- a synthetic, hand-authored (not
from a real FRET project) ladder of 25 requirements with generalized variable names (a-h, mode,
x, y), built specifically to exercise the LLM split-suggestion pipeline across the full range of
complexity it might encounter: SC01 is a bare two-variable implication with nothing to split;
SC25 bundles seven independent obligations (typed dispatch with its own exclusivity invariant,
a step-delayed response, a bounded response, an until-response, two typed comparisons, and a
biconditional) into one requirement. SC11-SC15 are a v2 addition bridging SC01-10 (which stayed
at "one or two variables, one operator" throughout) and SC16+ (which jumps straight to typed
dispatch/exclusivity/bounded operators) -- without them there was nothing in between.

Confirmed against the real tools, not just the importer: SC01/SC04/SC11/SC12/SC15 (simple-to-
medium end of the ladder) round-trip cleanly through both Strix and Kind2 realizability as
REALIZABLE. SC18 (first use of a bounded F[lo,hi] operator -- MLTL-style syntax, not plain LTL)
fails clearly in both, the same documented boundary as Ogma's/Kind2's known limitations elsewhere
in this project -- intentional, not a bug: "very difficult" should include the edges where the
pipeline's own real limits bite.

Also confirmed: any pt formula with a *nested* Y/O/S (not just the single top-level H every pt
formula starts with -- e.g. SC13's "(b S a)", SC14's "(Y a)"/"(O c)") fails Kind2 with a genuine
Lustre syntax error, not a semantic "unrealizable" verdict -- this is kind2_check.py's already-
documented limitation (`_translate_propositional` only translates <->/->/&/|/! ; it was never
meant to translate temporal operators, only `_strip_top_level_h` handles H, and only at the very
top), not something new this fixture introduced. Strix doesn't have this gap (SC14 gets a real
UNREALIZABLE verdict from it, not a parse error) since Spot/Strix/SPIN natively parse Y/O/S.

Previously (v1, 20 requirements), reference_check.py's find_undeclared_references flagged the
literal "FALSE" in formulas like "(O[0,4] (Z FALSE))" (then SC13/17/20, now SC18/22/25) as an
undeclared variable -- _LTL_KEYWORDS only listed "false"/"False", not the all-caps spelling FRET
itself uses in this exact idiom (confirmed in the real LiftPlusCruise fixture too). Fixed there,
not here; see test_reference_check.py.
"""

from pathlib import Path

from .conftest import requires_kind2, requires_strix

from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.kind2_check import check_realizability_kind2
from ltlsplitter.core.realizability import check_realizability_typed

_FIXTURE = Path(__file__).parent / "fixtures" / "splitter_complexity_ladder.json"


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
    """Regression test for the exact issue reported against this fixture: SC18/22/25 (then
    SC13/17/20, before SC11-15 were inserted) use the literal "FALSE" in their bounded-operator
    pt formulas (e.g. "(O[0,4] (Z FALSE))") and were flagged as an undeclared variable by
    import_split.py's reference check -- fixed in reference_check.py's _LTL_KEYWORDS."""
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
    aren't, e.g. SC18's bounded-operator syntax -- see the module docstring)."""
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("SC01_simple_implication")

    result = check_realizability_typed(req.ft_formula, fi.variables, fi.project)

    assert result.realizable is True


@requires_kind2
def test_simplest_requirement_is_kind2_realizable():
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("SC01_simple_implication")

    result = check_realizability_kind2([], [req.pt_formula], fi.variables)

    assert result.realizable is True
