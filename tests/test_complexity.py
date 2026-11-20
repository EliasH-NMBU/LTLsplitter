from ltlsplitter.core.complexity import formula_complexity


def test_counts_operators_and_half_weight_distinct_variables():
    # operators: H, ->, &, ! = 4 ; variables: a, b, c = 3 -> 4 + 1.5
    c = formula_complexity("(H (a -> (b & (! c))))")
    assert (c.operators, c.variables) == (4, 3)
    assert c.score == 5.5


def test_multi_char_operators_are_counted_once():
    c = formula_complexity("(G ((a <-> b) & (x != y) & (n <= 3)))")
    # G, <->, &, !=, &, <= = 6
    assert c.operators == 6


def test_repeated_variable_counts_once():
    assert formula_complexity("(G (a & a & a))").variables == 1


def test_bounded_operator_counts_once_and_constants_are_not_variables():
    c = formula_complexity("(H ((H (! x)) -> (O[0,12] (Z FALSE))))")
    # H, H, !, ->, O, Z = 6 ; variables: x only (FALSE excluded)
    assert (c.operators, c.variables) == (6, 1)


def test_declared_names_exclude_enum_literals():
    c = formula_complexity("(G ((state = s3) -> e))", declared_names={"state", "e"})
    assert c.variables == 2


def test_split_parts_are_each_smaller_than_the_original():
    original = formula_complexity("(H ((state = 2) -> ((((! slowdown) & halt) & alert) & (! turnoffUVC))))")
    part = formula_complexity("(H ((state = 2) -> halt))")
    assert part.score < original.score
