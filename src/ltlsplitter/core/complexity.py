from __future__ import annotations

import re
from dataclasses import dataclass

# Longest alternatives first, so "<->" isn't read as "<" + "->", or "!=" as "!" + "=".
_OPERATOR_RE = re.compile(r"<->|->|!=|<=|>=|&|\||!|=|<|>|\bxor\b|\b[GFXUHOSYZVWR]\b")
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_NON_VARIABLES = {"TRUE", "FALSE", "xor", "G", "F", "X", "U", "H", "O", "S", "Y", "Z", "V", "W", "R"}


@dataclass(frozen=True)
class Complexity:
    operators: int
    variables: int

    @property
    def score(self) -> float:
        return self.operators + 0.5 * self.variables


def formula_complexity(formula: str, declared_names: set[str] | None = None) -> Complexity:
    """operators + 0.5 * distinct variables. Operators are boolean/temporal/comparison
    operators, each occurrence counted (a bounded "O[0,12]" counts once). Variables are distinct
    identifiers -- restricted to declared_names when given, so enum literals and constants
    aren't counted."""
    operators = len(_OPERATOR_RE.findall(formula))
    identifiers = set(_IDENTIFIER_RE.findall(formula)) - _NON_VARIABLES
    if declared_names is not None:
        identifiers &= declared_names
    return Complexity(operators=operators, variables=len(identifiers))
