from __future__ import annotations

from ltlsplitter.core.models import FretRequirement, MonitorGroup

_MAX_NAME_VARS = 3


def suggest_groups(requirements: list[FretRequirement]) -> list[MonitorGroup]:
    """Clusters requirements that share at least one referenced variable (directly, or
    transitively through a chain of other requirements) into the same monitoring group --
    a deterministic, explainable starting point the user can then drag requirements out of or
    into by hand, rather than an LLM guess. Two requirements sharing a variable is exactly what
    makes them worth monitoring together: a single ROS2 Copilot node already has to subscribe to
    that variable's topic for one of them, so including the other costs nothing extra and keeps
    related obligations in one deployable package instead of scattered across several.

    Requirements that share no variable with anything else become their own single-member group
    (nothing to merge them with) -- not dropped, not bundled arbitrarily.
    """
    if not requirements:
        return []

    parent: dict[str, str] = {r.reqid: r.reqid for r in requirements}

    def find(reqid: str) -> str:
        while parent[reqid] != reqid:
            parent[reqid] = parent[parent[reqid]]
            reqid = parent[reqid]
        return reqid

    def union(a: str, b: str) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_a] = root_b

    by_variable: dict[str, list[str]] = {}
    for req in requirements:
        for var in req.variable_names:
            by_variable.setdefault(var, []).append(req.reqid)
    for reqids_sharing_a_variable in by_variable.values():
        for other in reqids_sharing_a_variable[1:]:
            union(reqids_sharing_a_variable[0], other)

    members_by_root: dict[str, list[str]] = {}
    root_order: list[str] = []
    for req in requirements:
        root = find(req.reqid)
        if root not in members_by_root:
            members_by_root[root] = []
            root_order.append(root)
        members_by_root[root].append(req.reqid)

    reqs_by_id = {r.reqid: r for r in requirements}
    groups = []
    for i, root in enumerate(root_order, start=1):
        member_ids = members_by_root[root]
        groups.append(MonitorGroup(name=f"Group {i}: {_group_label(member_ids, reqs_by_id)}", requirement_ids=member_ids))
    return groups


def _group_label(member_ids: list[str], reqs_by_id: dict[str, FretRequirement]) -> str:
    """The variables every member has in common (or, if that's empty -- e.g. a chain A-B-C
    where A and C share nothing directly -- every variable that appears anywhere in the group),
    so the suggested name explains *why* these requirements ended up together."""
    var_sets = [set(reqs_by_id[rid].variable_names) for rid in member_ids]
    shared = set.intersection(*var_sets) if len(var_sets) > 1 else var_sets[0]
    names = sorted(shared) if shared else sorted(set().union(*var_sets))
    if not names:
        return "no shared variables"
    label = ", ".join(names[:_MAX_NAME_VARS])
    return label + ("..." if len(names) > _MAX_NAME_VARS else "")
