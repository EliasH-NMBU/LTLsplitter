from ltlsplitter.core.reference_check import find_undeclared_references


def test_finds_undeclared_and_ignores_keywords_and_declared():
    formula = "G (request -> F response) and extra_var"
    assert find_undeclared_references(formula, {"request", "response"}) == ["extra_var"]


def test_no_undeclared_when_all_declared():
    assert find_undeclared_references("G (a -> F b)", {"a", "b"}) == []


def test_deduplicates_repeated_undeclared_tokens():
    assert find_undeclared_references("a and a and b", {"a"}) == ["b"]


def test_does_not_flag_all_caps_true_false_literals():
    """FRET itself spells the boolean literal all-caps in bounded-operator formulas, e.g.
    "(O[0,4] (Z FALSE))" (confirmed in the real LiftPlusCruise fixture) -- these must not be
    flagged as undeclared variables just because they're not in the declared set."""
    formula = "(H ((H (! a)) -> (O[0,4] (Z FALSE))))"
    assert find_undeclared_references(formula, {"a"}) == []
    assert find_undeclared_references("G (a -> TRUE)", {"a"}) == []
