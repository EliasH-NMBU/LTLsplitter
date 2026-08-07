from ltlsplitter.core.reference_check import find_undeclared_references


def test_finds_undeclared_and_ignores_keywords_and_declared():
    formula = "G (request -> F response) and extra_var"
    assert find_undeclared_references(formula, {"request", "response"}) == ["extra_var"]


def test_no_undeclared_when_all_declared():
    assert find_undeclared_references("G (a -> F b)", {"a", "b"}) == []


def test_deduplicates_repeated_undeclared_tokens():
    assert find_undeclared_references("a and a and b", {"a"}) == ["b"]
