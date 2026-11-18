from __future__ import annotations

from ltlsplitter.core.models import FretRequirement


def auto_sort_requirements(
    variable_groups: dict[str, list[str]], requirements: list[FretRequirement],
) -> dict[str, list[str]]:
    """Assigns each requirement to whichever variable group -- set up by hand, drag-and-drop,
    before this is called -- covers its variables, so requirements that need the same
    variables' topics end up in the same monitor package automatically.

    A requirement is assigned to a group only when all of the groups its variables touch is
    exactly one: a variable that isn't in any group yet doesn't block assignment (it just hasn't
    been organized yet), but a requirement whose variables span *two or more different* groups
    is genuinely ambiguous -- which one it belongs with is a real judgment call, not something
    to guess at -- so it's left out of the result entirely (the caller treats "not in any
    group's list" as "needs the user to place it by hand"). A requirement referencing no
    variable at all (or only ones in no group) is left out for the same reason: there's nothing
    to sort it by.
    """
    group_by_variable: dict[str, str] = {}
    for group_name, variable_names in variable_groups.items():
        for name in variable_names:
            group_by_variable[name] = group_name

    assigned: dict[str, list[str]] = {name: [] for name in variable_groups}
    for req in requirements:
        touched_groups = {group_by_variable[name] for name in req.variable_names if name in group_by_variable}
        if len(touched_groups) == 1:
            assigned[next(iter(touched_groups))].append(req.reqid)
    return assigned
