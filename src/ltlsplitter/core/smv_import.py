from __future__ import annotations

import re
from pathlib import Path

from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableType

_COMMENT_RE = re.compile(r"--[^\n]*")

# Every NuSMV/nuXmv top-level section keyword -- marks where a VAR block or an LTLSPEC formula
# must end, whichever comes first (a trailing ";" isn't actually required by nuXmv's own parser
# on the last statement in a file -- confirmed by running the real binary on a real benchmark
# file, ltlsat-polimi/krca1p1.smv, that ends in "))" with no final ";" at all).
_TOP_LEVEL_KEYWORDS = (
    "MODULE", "VAR", "IVAR", "FROZENVAR", "ASSIGN", "DEFINE", "TRANS", "INIT", "INVAR",
    "INVARSPEC", "FAIRNESS", "JUSTICE", "COMPASSION", "LTLSPEC", "CTLSPEC", "PSLSPEC", "COMPUTE",
)
_VAR_BLOCK_RE = re.compile(
    r"\b(?:VAR|IVAR|FROZENVAR)\b(?P<body>.*?)(?=\b(?:" + "|".join(_TOP_LEVEL_KEYWORDS) + r")\b|\Z)",
    re.DOTALL,
)
_LTLSPEC_RE = re.compile(
    r"\bLTLSPEC\b\s*(?:NAME\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*:=\s*)?"
    r"(?P<formula>.*?)(?:;|(?=\b(?:" + "|".join(_TOP_LEVEL_KEYWORDS) + r")\b)|\Z)",
    re.DOTALL,
)
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_PAST_TIME_OP_RE = re.compile(r"\b[HOSYZ]\b")

# Never real variable names -- LTL/SMV keywords and literals that can show up as bare
# identifiers inside a formula.
_RESERVED_WORDS = {
    "TRUE", "FALSE", "G", "F", "X", "U", "V", "W", "R", "H", "O", "S", "Y", "Z",
    "NAME", "LTLSPEC", "CTLSPEC", "PSLSPEC", "COMPUTE", "MODULE", "VAR", "IVAR", "FROZENVAR",
    "ASSIGN", "DEFINE", "TRANS", "INIT", "INVAR", "FAIRNESS", "JUSTICE", "COMPASSION",
    "xor", "xnor", "mod", "next", "init", "union", "in",
}


class InvalidSmvFileError(ValueError):
    """The selected file doesn't look like a NuSMV/nuXmv .smv file with any LTLSPEC in it."""


def _strip_comments(text: str) -> str:
    return _COMMENT_RE.sub("", text)


def _parse_type(type_text: str) -> tuple[VariableType, float | None, float | None, list[str]]:
    """Returns (type, min_value, max_value, enum_values) for one VAR declaration's type text --
    "boolean", "0..10", "{idle, running, done}", or "real"/"integer"/anything else, which falls
    back to a plain, unbounded int (confirmed-safe default -- every tool here treats an
    unrecognized numeric type as "just an int" already, see realizability.py's _smv_var_type)."""
    type_text = type_text.strip()
    if type_text == "boolean":
        return VariableType.BOOL, None, None, []
    if type_text in ("real",):
        return VariableType.FLOAT, None, None, []
    range_match = re.fullmatch(r"(-?\d+)\s*\.\.\s*(-?\d+)", type_text)
    if range_match:
        return VariableType.INT, float(range_match.group(1)), float(range_match.group(2)), []
    enum_match = re.fullmatch(r"\{(.*)\}", type_text, re.DOTALL)
    if enum_match:
        values = [v.strip() for v in enum_match.group(1).split(",") if v.strip()]
        return VariableType.ENUM, None, None, values
    return VariableType.INT, None, None, []


def _parse_variables(content: str) -> list[Variable]:
    variables: list[Variable] = []
    seen: set[str] = set()
    for block_match in _VAR_BLOCK_RE.finditer(content):
        for declaration in block_match.group("body").split(";"):
            name, sep, type_text = declaration.partition(":")
            name = name.strip()
            if not sep or not name or name in seen:
                continue
            seen.add(name)
            var_type, lo, hi, enum_values = _parse_type(type_text)
            variables.append(Variable(name=name, type=var_type, min_value=lo, max_value=hi, enum_values=enum_values))
    return variables


def _referenced_identifiers(formula: str) -> list[str]:
    return [t for t in _IDENTIFIER_RE.findall(formula) if t not in _RESERVED_WORDS]


def import_smv_file(path: str | Path) -> FretImport:
    """Parses a plain NuSMV/nuXmv .smv file -- `VAR` declarations plus one or more `LTLSPEC`
    statements -- into our model, so test fixtures and other tools' output (anything that
    already shells out to nuXmv, not just FRET's own JSON export) can be imported directly.

    Each `LTLSPEC` becomes one requirement. A declared variable always ends up with
    role=Variable's own default (INPUT) -- plain SMV has no FRET-style idType distinguishing
    input/output/internal, so there's nothing honest to infer it from; correct it by hand on
    page 1 if a requirement's variables need a different role for stage 3's realizability check.

    A requirement's formula goes to **pt_formula** if it contains any past-time operator
    (H/O/S/Y/Z) anywhere -- Spot/SPIN can't parse past operators at all, confirmed elsewhere in
    this codebase, so a formula using even one is only ever checkable via nuXmv. Everything else
    (no past operator found) goes to **ft_formula** instead, left for the LLM/validation stages
    to treat as a pure future-time formula. Only one of the two is ever filled in -- there is no
    general past<->future LTL translation here (an open research problem, see
    docs/pipeline-design-research.md), so this never guesses the other form."""
    path = Path(path)
    try:
        raw_text = path.read_text()
    except OSError as exc:
        raise InvalidSmvFileError(f"Couldn't read '{path}': {exc}") from exc

    content = _strip_comments(raw_text)
    ltlspec_matches = list(_LTLSPEC_RE.finditer(content))
    if not ltlspec_matches:
        raise InvalidSmvFileError(
            f"'{path}' doesn't look like a NuSMV/nuXmv file -- found no \"LTLSPEC ...;\" statement."
        )

    variables = _parse_variables(content)
    declared_names = {v.name for v in variables}
    # An enum literal ("state = s3") is a bare identifier too, but it's s3 the *value*, not a
    # variable named s3 -- confirmed against a real nuXmv example (growing-counter-integer.smv,
    # `VAR state : {s0,s1,s2,s3}; ... LTLSPEC G F (state = s3)`), where treating it as an
    # undeclared variable would wrongly add a second, fictitious "s3" boolean alongside the
    # real enum.
    enum_literals = {value for v in variables if v.type == VariableType.ENUM for value in v.enum_values}

    requirements: list[FretRequirement] = []
    for i, match in enumerate(ltlspec_matches, start=1):
        formula = match.group("formula").strip()
        reqid = match.group("name") or f"smv_req_{i}"
        is_past_time = bool(_PAST_TIME_OP_RE.search(formula))
        referenced = [t for t in dict.fromkeys(_referenced_identifiers(formula)) if t not in enum_literals]

        # A referenced identifier nothing declared (common for a bare list of formulas with no
        # VAR section at all) is still a real variable -- just an undeclared one, defaulted to
        # boolean rather than silently dropped from variable_names.
        for name in referenced:
            if name not in declared_names:
                declared_names.add(name)
                variables.append(Variable(name=name, type=VariableType.BOOL))

        requirements.append(
            FretRequirement(
                reqid=reqid,
                fulltext=f"(imported from {path.name}) {formula}",
                pt_formula=formula if is_past_time else "",
                ft_formula="" if is_past_time else formula,
                variable_names=referenced,
            )
        )

    return FretImport(project=path.stem, requirements=requirements, variables=variables)
