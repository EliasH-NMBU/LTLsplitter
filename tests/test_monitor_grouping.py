from ltlsplitter.core.models import FretRequirement
from ltlsplitter.core.monitor_grouping import auto_sort_requirements


def _req(reqid: str, variables: list[str]) -> FretRequirement:
    return FretRequirement(
        reqid=reqid, fulltext="...", pt_formula="(H x)", ft_formula="(G x)", variable_names=variables,
    )


def test_empty_input_returns_empty_groups():
    assert auto_sort_requirements({}, []) == {}
    assert auto_sort_requirements({"Group A": ["a"]}, []) == {"Group A": []}


def test_requirement_whose_variables_are_all_in_one_group_is_assigned_there():
    groups = {"Group A": ["a", "b"]}
    reqs = [_req("r1", ["a", "b"])]

    result = auto_sort_requirements(groups, reqs)

    assert result == {"Group A": ["r1"]}


def test_requirement_spanning_two_groups_is_left_unassigned():
    """The example straight from the request: two variables, each in a different group --
    genuinely ambiguous, so it must not show up in either group's list."""
    groups = {"Group A": ["a"], "Group B": ["b"]}
    reqs = [_req("r1", ["a", "b"])]

    result = auto_sort_requirements(groups, reqs)

    assert result == {"Group A": [], "Group B": []}


def test_requirement_with_no_variables_in_any_group_is_left_unassigned():
    groups = {"Group A": ["a"]}
    reqs = [_req("r1", ["z"]), _req("r2", [])]

    result = auto_sort_requirements(groups, reqs)

    assert result == {"Group A": []}


def test_an_unassigned_variable_does_not_block_assignment():
    """r1 uses "a" (grouped) and "z" (still in the unassigned pool, i.e. not a key in
    variable_groups at all) -- only one *group* is touched, so it's still assignable."""
    groups = {"Group A": ["a"]}
    reqs = [_req("r1", ["a", "z"])]

    result = auto_sort_requirements(groups, reqs)

    assert result == {"Group A": ["r1"]}


def test_internal_variables_not_in_any_group_do_not_block_assignment():
    """Mirrors how the caller builds variable_groups: an internal variable is never placed in
    any group (it's excluded from the variable pool entirely), so it behaves exactly like any
    other not-yet-grouped variable here -- present on the requirement, absent from every
    group's list."""
    groups = {"Group A": ["a"]}
    reqs = [_req("r1", ["a", "derived_internal_var"])]

    result = auto_sort_requirements(groups, reqs)

    assert result == {"Group A": ["r1"]}


def test_output_order_is_deterministic_by_first_appearance():
    groups = {"Group A": ["a"]}
    reqs = [_req("r1", ["a"]), _req("r2", ["z"]), _req("r3", ["a"])]

    result = auto_sort_requirements(groups, reqs)

    assert result == {"Group A": ["r1", "r3"]}
