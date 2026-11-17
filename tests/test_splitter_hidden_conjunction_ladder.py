"""Tests for tests/fixtures/splitter_hidden_conjunction_ladder.json -- a synthetic, hand-authored
ladder of 12 requirements where NO formula contains a top-level or nested "&" anywhere.

Why this fixture exists: splitter_complexity_ladder.json's requirements, however entangled their
*consequents* are made to be (see that file's own docstring), still always expose their
independent obligations as syntactic "&"-conjuncts somewhere in the formula -- a purely
syntactic/variable-dependency splitter (Finkbeiner-style conjunct clustering) can always find
*a* conjunction to pull apart, even where doing so isn't the semantically interesting split. This
fixture removes that crutch entirely: every requirement here is built from only "->", "<->", "!",
"|", and typed comparisons -- a real, non-degenerate decomposition exists for every one of them,
but reaching it requires actually *deriving* a conjunction via a known LTL law (splitting a
biconditional into two implications, distributing an implication over a disjunctive antecedent,
De Morgan's law on a negated disjunction, or exportation to introduce a trigger-guard conjunction
that wasn't written anywhere in the original) rather than just reading one off the syntax.

Every decomposition below was brute-force-verified (all boolean valuations of every variable
involved, treating each typed comparison like "mode = 0" as its own opaque atom) before this
fixture was written, and the hardest rung (HD10) was additionally confirmed end-to-end against
the real nuXmv/Spot/SPIN binaries via validate_decomposition.

Nesting safety (why pt/ft always line up): every requirement here is a pure boolean-state
condition -- no X/F/U/Y/O/S/Z anywhere -- so the pt and ft forms are always IDENTICAL other than
the leading H vs G, with zero risk of an asymmetric past/future translation (unlike e.g. the main
ladder's precedence/until/bounded-response idioms, where pt and ft genuinely differ in structure).
"""

from pathlib import Path

from .conftest import requires_kind2, requires_strix

from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.kind2_check import check_realizability_kind2
from ltlsplitter.core.realizability import check_realizability_typed

_FIXTURE = Path(__file__).parent / "fixtures" / "splitter_hidden_conjunction_ladder.json"


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


def test_imports_cleanly_with_twelve_requirements():
    fi = import_fret_file(_FIXTURE)

    assert fi.project == "SplitterHiddenConjunctionLadder"
    assert len(fi.requirements) == 12
    assert len(fi.leaf_requirements()) == 12  # none pre-split -- every one is a leaf
    assert len(fi.variables) == 6


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


def test_no_requirement_contains_a_conjunction():
    """The whole point of this fixture: nothing here is already split-able by looking for a "&"
    -- a naive syntactic splitter has nothing to grab onto, since a real decomposition (where one
    exists) has to be derived via a logical law, not read off the formula's surface structure."""
    fi = import_fret_file(_FIXTURE)

    for req in fi.requirements:
        assert "&" not in req.pt_formula, f"{req.reqid}: pt formula contains '&'"
        assert "&" not in req.ft_formula, f"{req.reqid}: ft formula contains '&'"


def test_pt_and_ft_forms_are_identical_other_than_the_leading_operator():
    """Every requirement here is a pure boolean-state condition (no X/F/U/Y/O/S/Z), so pt and ft
    must be the exact same text once the single leading "(H " / "(G " is stripped -- confirms
    none of these accidentally drifted into needing a real past/future translation."""
    fi = import_fret_file(_FIXTURE)

    for req in fi.requirements:
        assert req.pt_formula.startswith("(H "), req.reqid
        assert req.ft_formula.startswith("(G "), req.reqid
        assert req.pt_formula[3:] == req.ft_formula[3:], f"{req.reqid}: pt/ft diverge beyond H/G"


@requires_strix
def test_simplest_requirement_is_strix_realizable():
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("HD01_pure_biconditional")

    result = check_realizability_typed(req.ft_formula, fi.variables, fi.project)

    assert result.realizable is True


@requires_kind2
def test_simplest_requirement_is_kind2_realizable():
    fi = import_fret_file(_FIXTURE)
    req = fi.requirement("HD01_pure_biconditional")

    result = check_realizability_kind2([], [req.pt_formula], fi.variables)

    assert result.realizable is True
