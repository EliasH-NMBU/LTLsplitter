from __future__ import annotations

from ltlsplitter.core.models import ConsistencyResult, RealizabilityResult, Specification


def check_consistency(specs: list[Specification]) -> ConsistencyResult:
    """Satisfiability check across a set of specs, intended to shell out to nuXmv."""
    raise NotImplementedError


def check_realizability(spec: Specification, inputs: list[str], outputs: list[str]) -> RealizabilityResult:
    """GR(1) realizability check for a single spec, intended to shell out to Strix or Spot's ltlsynt."""
    raise NotImplementedError
