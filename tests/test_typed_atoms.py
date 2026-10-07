from ltlsplitter.core.typed_atoms import TypedComparison, extract_typed_comparisons


def test_extract_typed_comparisons_finds_each_distinct_comparison():
    formula = "(classifier = 1) -> (dgt_7 -> (state = 1))"
    comparisons, leftover = extract_typed_comparisons(formula, {"classifier", "state", "distance_to_target"})

    assert comparisons == [
        TypedComparison(text="classifier = 1", variable="classifier"),
        TypedComparison(text="state = 1", variable="state"),
    ]
    assert leftover == []


def test_extract_typed_comparisons_deduplicates_repeated_comparisons():
    formula = "(state = 1) -> ((state = 1) | (state = 2))"
    comparisons, _ = extract_typed_comparisons(formula, {"state"})

    assert [c.text for c in comparisons] == ["state = 1", "state = 2"]


def test_extract_typed_comparisons_reports_leftover_for_unsupported_shapes():
    formula = "distance_to_target + 1 > 3"
    comparisons, leftover = extract_typed_comparisons(formula, {"distance_to_target"})

    assert comparisons == []
    assert leftover == ["distance_to_target"]


def test_extract_typed_comparisons_ignores_unreferenced_typed_names():
    formula = "G x"
    comparisons, leftover = extract_typed_comparisons(formula, {"state"})

    assert comparisons == []
    assert leftover == []


def test_extract_typed_comparisons_handles_empty_typed_names():
    comparisons, leftover = extract_typed_comparisons("G (state = 1)", set())

    assert comparisons == []
    assert leftover == []


def test_extract_typed_comparisons_supports_relational_operators():
    formula = "(distance != 0) & (distance <= 5) & (distance >= 1) & (distance < 10) & (distance > 2)"
    comparisons, leftover = extract_typed_comparisons(formula, {"distance"})

    assert [c.text for c in comparisons] == [
        "distance != 0", "distance <= 5", "distance >= 1", "distance < 10", "distance > 2",
    ]
    assert leftover == []
