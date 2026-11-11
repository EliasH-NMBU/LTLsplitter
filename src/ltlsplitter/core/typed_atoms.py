from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(frozen=True)
class TypedComparison:
    """One `variable OP literal` comparison (e.g. "classifier = 1") or `variable OP variable`
    comparison (e.g. "y = mode") found in a formula."""

    text: str
    variable: str
    other_variable: str | None = None
    """The right-hand variable for a `variable OP variable` comparison -- None for an ordinary
    `variable OP literal` comparison, where the right-hand side is a number instead."""


def extract_typed_comparisons(
    formula: str, typed_variable_names: set[str]
) -> tuple[list[TypedComparison], list[str]]:
    """Finds every "name OP literal" or "name OP name2" comparison in `formula` for the given
    typed (non-boolean) variable names -- the shapes FRET/nuXmv write for equality/relational
    tests over typed variables, and the only shapes this project's boolean-only-LTL-tool
    handling (Spot/SPIN/Strix) attempts to support. Also reports which typed variable names are
    still referenced *outside* any matched comparison (by masking every match out of the formula
    first, then checking what typed-variable tokens remain) -- a sign the formula uses something
    this project doesn't attempt to handle (compound arithmetic across variables, etc.), which
    callers should treat as unsupported rather than silently mishandle."""
    if not typed_variable_names:
        return [], []

    names_pattern = "|".join(re.escape(n) for n in sorted(typed_variable_names, key=len, reverse=True))
    op_pattern = r"(?:=|!=|<=|>=|<|>)"
    pattern = re.compile(rf"\b(?:{names_pattern})\s*{op_pattern}\s*(?:-?\d+(?:\.\d+)?|(?:{names_pattern}))\b")
    variable_pattern = re.compile(rf"\b({names_pattern})\b")

    comparisons: dict[str, TypedComparison] = {}
    for match in pattern.finditer(formula):
        text = match.group(0)
        if text in comparisons:
            continue
        found = variable_pattern.findall(text)
        other_variable = found[1] if len(found) > 1 else None
        comparisons[text] = TypedComparison(text=text, variable=found[0], other_variable=other_variable)

    masked = pattern.sub(" ", formula)
    leftover_tokens = set(_IDENTIFIER_RE.findall(masked))
    leftover = sorted(typed_variable_names & leftover_tokens)

    return list(comparisons.values()), leftover
