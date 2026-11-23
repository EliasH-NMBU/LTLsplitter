from __future__ import annotations

import json
import re
from pathlib import Path

from ltlsplitter.core.models import FretImport, FretRequirement, SubFormula, Variable, VariableRole, VariableType

_DATA_TYPE_MAP = {
    "boolean": VariableType.BOOL,
    "bool": VariableType.BOOL,
    "integer": VariableType.INT,
    "int": VariableType.INT,
    "double": VariableType.FLOAT,
    "float": VariableType.FLOAT,
    "enum": VariableType.ENUM,
    "string": VariableType.ENUM,
}

_ID_TYPE_MAP = {
    "Input": VariableRole.INPUT,
    "Output": VariableRole.OUTPUT,
    "Internal": VariableRole.INTERNAL,
}


def _normalize_type_field(value) -> str:
    """Some real FRET exports (confirmed against the FiniteStateMachine and LiquidMixer case
    studies shipped with FRET itself, not hypothetical) wrap a variable's dataType/idType in a
    single-element list instead of a bare string. Using that list directly as a dict key raises
    TypeError (list is unhashable), so this unwraps it first."""
    if isinstance(value, list):
        return value[0] if value else ""
    return value or ""


class InvalidFretFileError(ValueError):
    """The selected file doesn't look like a FRET project export."""


_ASSUMPTION_RE = re.compile(r"assumption|assume", re.IGNORECASE)


def _is_assumption_heuristic(reqid: str, fulltext: str) -> bool:
    """FRET's export has no structural field distinguishing environment assumptions from system
    guarantees -- only a naming convention seen in real data (e.g. "classifier_assumption"). This
    is a starting guess the user can correct via the GUI checkbox, not a silent final answer."""
    return bool(_ASSUMPTION_RE.search(reqid) or _ASSUMPTION_RE.search(fulltext))


def _pt_formula(semantics: dict) -> str:
    return semantics.get("ptExpanded") or semantics.get("pt") or ""


def _ft_formula(semantics: dict) -> str:
    """`ft`/`ftExpanded` encode FRET's finite-trace semantics via a special "LAST" atomic
    proposition (e.g. "LAST V (...)") that downstream tools (Spot, SPIN) don't know about.
    `ftInfAUExpanded` is the same obligation in plain infinite-trace future LTL (G/F/X/U), which
    is the portable form every tool here actually understands -- confirmed against a real FRET
    export, not assumed."""
    return semantics.get("ftInfAUExpanded") or semantics.get("ftExpanded") or semantics.get("ft") or ""


_COMPARISON_OPS = r"(?:<=|>=|!=|=|<(?!-)|(?<![-<])>)"
_NUMBER_RE = r"-?\d+(?:\.\d+)?"


def infer_variable_type(name: str, formulas: list[str]) -> VariableType:
    """Type of a variable FRET left untyped, from how the formulas use it: a variable that is
    only ever used as a truth value ("! x", "x -> y") is boolean; one compared with a number is
    an integer (or float, for a decimal). Without this, untyped variables became integers and
    nuXmv rejected every "! x" with "illegal operand type", and Spot/SPIN refused the atoms."""
    escaped = re.escape(name)
    compared = re.compile(
        rf"\b{escaped}\s*{_COMPARISON_OPS}\s*(?P<a>[^\s()]+)|(?P<b>[^\s()]+)\s*{_COMPARISON_OPS}\s*{escaped}\b"
    )
    other_sides = [m.group("a") or m.group("b") for f in formulas for m in compared.finditer(f)]
    if not other_sides:
        return VariableType.BOOL
    if any(re.fullmatch(_NUMBER_RE, o) and "." in o for o in other_sides):
        return VariableType.FLOAT
    return VariableType.INT


def import_fret_file(path: str | Path) -> FretImport:
    """Parses a FRET project export JSON (FRET's own "Export Requirements/Variables as JSON"
    format: a top-level {"requirements": [...], "variables": [...]} object) into our model."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidFretFileError(f"Couldn't read '{path}' as JSON: {exc}") from exc

    if not isinstance(data, dict) or "requirements" not in data or "variables" not in data:
        raise InvalidFretFileError(
            f"'{path}' doesn't look like a FRET project export -- expected a JSON object with "
            "\"requirements\" and \"variables\" keys."
        )

    requirements = []
    for req in data["requirements"]:
        semantics = req.get("semantics", {})
        if "is_assumption" in req:
            is_assumption = bool(req["is_assumption"])
        else:
            is_assumption = _is_assumption_heuristic(req["reqid"], req.get("fulltext", ""))
        requirements.append(
            FretRequirement(
                reqid=req["reqid"],
                fulltext=req.get("fulltext", ""),
                pt_formula=_pt_formula(semantics),
                ft_formula=_ft_formula(semantics),
                variable_names=list(semantics.get("variables", [])),
                parent_reqid=req.get("parent_reqid", ""),
                is_assumption=is_assumption,
            )
        )

    formulas = [f for r in requirements for f in (r.pt_formula, r.ft_formula) if f]
    variables = []
    for var in data["variables"]:
        data_type = _normalize_type_field(var.get("dataType"))
        if data_type in _DATA_TYPE_MAP:
            var_type = _DATA_TYPE_MAP[data_type]
        elif not data_type:
            # FRET leaves dataType empty until the variable is mapped in its Variable Mapping
            # view (seen in the real UseCase6 export: every variable untyped).
            var_type = infer_variable_type(var["variable_name"], formulas)
        else:
            var_type = VariableType.INT
        variables.append(
            Variable(
                name=var["variable_name"],
                type=var_type,
                role=_ID_TYPE_MAP.get(_normalize_type_field(var.get("idType")), VariableRole.INPUT),
                assignment=var.get("assignment") or None,
                copilot_assignment=var.get("copilotAssignment") or None,
                # Not FRET fields -- only present when this project wrote the file itself
                # (save_session below), so a variable added in the GUI round-trips fully.
                topic=var.get("topic", ""),
                min_value=var.get("min_value"),
                max_value=var.get("max_value"),
                enum_values=list(var.get("enum_values", [])),
            )
        )

    project = ""
    if data["requirements"]:
        project = data["requirements"][0].get("project", "")
    elif data["variables"]:
        project = data["variables"][0].get("project", "")

    return FretImport(project=project, requirements=requirements, variables=variables)


_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")


def _referenced_variable_names(sub: SubFormula, declared_names: set[str]) -> list[str]:
    tokens = _IDENTIFIER_RE.findall(sub.pt_formula + " " + sub.ft_formula)
    return sorted({t for t in tokens if t in declared_names})


_REVERSE_DATA_TYPE_MAP = {
    VariableType.BOOL: "boolean",
    VariableType.INT: "integer",
    VariableType.FLOAT: "double",
    VariableType.ENUM: "enum",
}
_REVERSE_ID_TYPE_MAP = {role: name for name, role in _ID_TYPE_MAP.items()}


def referenced_variable_names(pt_formula: str, ft_formula: str, declared_names: set[str]) -> list[str]:
    """Declared variables a requirement's formulas mention -- what FRET stores as
    semantics.variables, recomputed whenever a formula is written or edited here."""
    return _referenced_variable_names(SubFormula(id="", pt_formula=pt_formula, ft_formula=ft_formula), declared_names)


def _new_requirement_dict(req: FretRequirement, project: str) -> dict:
    return {
        "reqid": req.reqid,
        "parent_reqid": req.parent_reqid,
        "project": project,
        "fulltext": req.fulltext,
        "is_assumption": req.is_assumption,
        "semantics": {
            "pt": req.pt_formula,
            "ptExpanded": req.pt_formula,
            "ft": req.ft_formula,
            "ftExpanded": req.ft_formula,
            "ftInfAUExpanded": req.ft_formula,
            "variables": list(req.variable_names),
        },
    }


def _patch_requirement_dict(entry: dict, req: FretRequirement) -> dict:
    """Writes the in-memory requirement's values onto a copy of its original FRET entry. Only
    the formula fields this project reads get overwritten, and only when they actually changed,
    so an untouched requirement keeps FRET's own export byte-for-byte. An edited one is marked
    `ltlsplitter_edited`: FRET's other derived fields (CoCoSpecCode, the *BtwExpanded variants,
    ...) still describe the old formula and can't be regenerated outside FRET."""
    entry = json.loads(json.dumps(entry))
    entry["fulltext"] = req.fulltext
    entry["is_assumption"] = req.is_assumption
    if req.parent_reqid:
        entry["parent_reqid"] = req.parent_reqid
    semantics = entry.setdefault("semantics", {})
    edited = False
    if req.pt_formula != _pt_formula(semantics):
        semantics["pt"] = semantics["ptExpanded"] = req.pt_formula
        edited = True
    if req.ft_formula != _ft_formula(semantics):
        semantics["ft"] = semantics["ftExpanded"] = semantics["ftInfAUExpanded"] = req.ft_formula
        edited = True
    if edited:
        semantics["variables"] = list(req.variable_names)
        entry["ltlsplitter_edited"] = True
    return entry


def _variable_dict(var: Variable, project: str, entry: dict | None = None) -> dict:
    entry = json.loads(json.dumps(entry)) if entry else {"project": project, "variable_name": var.name}
    # Only rewritten when the parsed value differs, so FRET's own spellings ("double",
    # ["boolean"], ...) of an untouched variable are kept as they were.
    if _DATA_TYPE_MAP.get(_normalize_type_field(entry.get("dataType"))) != var.type:
        entry["dataType"] = _REVERSE_DATA_TYPE_MAP[var.type]
    if _ID_TYPE_MAP.get(_normalize_type_field(entry.get("idType"))) != var.role:
        entry["idType"] = _REVERSE_ID_TYPE_MAP[var.role]
    if (entry.get("assignment") or None) != var.assignment:
        entry["assignment"] = var.assignment or ""
    if (entry.get("copilotAssignment") or None) != var.copilot_assignment:
        entry["copilotAssignment"] = var.copilot_assignment or ""
    if var.topic:
        entry["topic"] = var.topic
    if var.min_value is not None:
        entry["min_value"] = var.min_value
    if var.max_value is not None:
        entry["max_value"] = var.max_value
    if var.enum_values:
        entry["enum_values"] = list(var.enum_values)
    return entry


def _read_source(source_path: str | Path | None) -> dict:
    """The file the session was loaded from, used as the base so FRET's own fields (rationale,
    status, CoCoSpec code, ...) survive the save. A .smv import has no JSON to start from, so
    the save is built from the in-memory model alone."""
    if not source_path or Path(source_path).suffix.lower() != ".json":
        return {"requirements": [], "variables": []}
    try:
        data = json.loads(Path(source_path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidFretFileError(f"Couldn't read '{source_path}' as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InvalidFretFileError(f"'{source_path}' doesn't look like a FRET project export.")
    return data


def save_session(fret_import: FretImport, output_path: str | Path, source_path: str | Path | None = None) -> None:
    """Writes the whole in-memory session to `output_path` in FRET export format: every
    requirement (edited originals, splits, ones added from natural language), every variable
    (including ones added in the GUI), assumption flags, and deletions. Requirements and
    variables that came from `source_path` keep their original FRET fields; `source_path`
    itself is only read, unless it *is* `output_path` (the session's own save file)."""
    data = _read_source(source_path)
    project = fret_import.project

    source_reqs = {r.get("reqid"): r for r in data.get("requirements", [])}
    data["requirements"] = [
        _patch_requirement_dict(source_reqs[req.reqid], req) if req.reqid in source_reqs
        else _new_requirement_dict(req, project)
        for req in fret_import.requirements
    ]

    source_vars = {v.get("variable_name"): v for v in data.get("variables", [])}
    data["variables"] = [_variable_dict(var, project, source_vars.get(var.name)) for var in fret_import.variables]

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
