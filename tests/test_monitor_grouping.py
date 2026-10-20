from ltlsplitter.core.models import FretRequirement
from ltlsplitter.core.monitor_grouping import suggest_groups


def _req(reqid: str, variables: list[str]) -> FretRequirement:
    return FretRequirement(
        reqid=reqid, fulltext="...", pt_formula="(H x)", ft_formula="(G x)", variable_names=variables,
    )


def test_empty_input_returns_no_groups():
    assert suggest_groups([]) == []


def test_requirements_sharing_a_variable_end_up_in_the_same_group():
    reqs = [_req("r1", ["a", "b"]), _req("r2", ["b", "c"])]

    groups = suggest_groups(reqs)

    assert len(groups) == 1
    assert set(groups[0].requirement_ids) == {"r1", "r2"}


def test_requirements_sharing_no_variable_end_up_in_separate_groups():
    reqs = [_req("r1", ["a"]), _req("r2", ["b"])]

    groups = suggest_groups(reqs)

    assert len(groups) == 2
    assert {tuple(g.requirement_ids) for g in groups} == {("r1",), ("r2",)}


def test_shared_variables_chain_transitively_through_a_middle_requirement():
    """r1 and r3 share nothing directly, but both connect to r2 -- all three belong together,
    since r2's monitor already has to subscribe to both variables' topics."""
    reqs = [_req("r1", ["a"]), _req("r2", ["a", "b"]), _req("r3", ["b"])]

    groups = suggest_groups(reqs)

    assert len(groups) == 1
    assert set(groups[0].requirement_ids) == {"r1", "r2", "r3"}


def test_a_requirement_with_no_variables_gets_its_own_group():
    reqs = [_req("r1", []), _req("r2", ["a"])]

    groups = suggest_groups(reqs)

    assert len(groups) == 2


def test_group_name_reflects_the_shared_variable():
    reqs = [_req("r1", ["classifier", "state"]), _req("r2", ["classifier"])]

    groups = suggest_groups(reqs)

    assert len(groups) == 1
    assert "classifier" in groups[0].name


def test_output_order_is_deterministic_by_first_appearance():
    reqs = [_req("r1", ["a"]), _req("r2", ["b"]), _req("r3", ["a"])]

    groups = suggest_groups(reqs)

    # r1/r3 (variable "a") must appear before r2 (variable "b") -- r1 appeared first.
    assert groups[0].requirement_ids == ["r1", "r3"]
    assert groups[1].requirement_ids == ["r2"]
