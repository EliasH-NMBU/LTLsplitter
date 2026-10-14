"""Tests for tests/fixtures/splitter_complexity_ladder.json -- a synthetic, hand-authored (not
from a real FRET project) ladder of 20 requirements with generalized variable names (a-h, mode,
x, y), built specifically to exercise the LLM split-suggestion pipeline across the full range of
complexity it might encounter: SC01 is a bare two-variable implication with nothing to split;
SC20 bundles seven independent obligations (typed dispatch with its own exclusivity invariant,
a step-delayed response, a bounded response, an until-response, two typed comparisons, and a
biconditional) into one requirement.

Confirmed against the real tools, not just the importer: SC01/SC04 (simple end of the ladder)
round-trip cleanly through both Strix and Kind2 realizability as REALIZABLE. SC13 (first use of
a bounded F[lo,hi] operator -- MLTL-style syntax, not plain LTL) fails clearly in both, the same
documented boundary as Ogma's/Kind2's known limitations elsewhere in this project -- intentional,
not a bug: "very difficult" should include the edges where the pipeline's own real limits bite.
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


def test_imports_cleanly_with_twenty_requirements():
    fi = import_fret_file(_FIXTURE)

    assert fi.project == "SplitterComplexityLadder"
    assert len(fi.requirements) == 20
    assert len(fi.leaf_requirements()) == 20  # none pre-split -- every one is a leaf
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
    aren't, e.g. SC13's bounded-operator syntax -- see the module docstring)."""
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
