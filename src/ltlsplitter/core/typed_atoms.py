from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


@dataclass(frozen=True)
class TypedComparison:
    """One `variable OP literal` comparison found in a formula, e.g. "classifier = 1"."""

    text: str
    variable: str


def extract_typed_comparisons(
    formula: str, typed_variable_names: set[str]
) -> tuple[list[TypedComparison], list[str]]:
    """Finds every "name OP literal" comparison in `formula` for the given typed (non-boolean)
    variable names -- the shape FRET/nuXmv write for equality/relational tests over typed
    variables, and the only shape this project's boolean-only-LTL-tool handling (Spot/SPIN/
    Strix) attempts to support. Also reports which typed variable names are still referenced
    *outside* any matched comparison (by masking every match out of the formula first, then
    checking what typed-variable tokens remain) -- a sign the formula uses something this
    project doesn't attempt to handle (compound arithmetic across variables, etc.), which
    callers should treat as unsupported rather than silently mishandle."""
    if not typed_variable_names:
        return [], []

    names_pattern = "|".join(re.escape(n) for n in sorted(typed_variable_names, key=len, reverse=True))
    pattern = re.compile(rf"\b(?:{names_pattern})\s*(?:=|!=|<=|>=|<|>)\s*-?\d+(?:\.\d+)?\b")
    variable_pattern = re.compile(rf"\b({names_pattern})\b")

    comparisons: dict[str, TypedComparison] = {}
    for match in pattern.finditer(formula):
        text = match.group(0)
        if text not in comparisons:
            variable = variable_pattern.search(text).group(1)
            comparisons[text] = TypedComparison(text=text, variable=variable)

    masked = pattern.sub(" ", formula)
    leftover_tokens = set(_IDENTIFIER_RE.findall(masked))
    leftover = sorted(typed_variable_names & leftover_tokens)

    return list(comparisons.values()), leftover
