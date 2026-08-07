from __future__ import annotations

import re

_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")

# Common LTL/propositional-logic keywords and operator spellings that are not
# variable references, so they shouldn't be flagged as undeclared.
_LTL_KEYWORDS = {
    "G", "F", "X", "U", "R", "W",
    "true", "false", "True", "False",
    "and", "or", "not", "implies", "iff", "xor",
    "next", "until", "release", "always", "eventually", "globally", "finally",
}


def find_undeclared_references(formula: str, declared_names: set[str]) -> list[str]:
    """Heuristic scan for identifier-like tokens in an LTL formula that aren't
    declared variables or known keywords. Not a real parser — for surfacing
    likely typos in the GUI, not for correctness guarantees."""
    tokens = _IDENTIFIER_RE.findall(formula)
    undeclared = [t for t in tokens if t not in declared_names and t not in _LTL_KEYWORDS]
    seen: list[str] = []
    for token in undeclared:
        if token not in seen:
            seen.append(token)
    return seen
