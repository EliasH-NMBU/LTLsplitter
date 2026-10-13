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

    variables = []
    for var in data["variables"]:
        variables.append(
            Variable(
                name=var["variable_name"],
                type=_DATA_TYPE_MAP.get(var.get("dataType", ""), VariableType.INT),
                role=_ID_TYPE_MAP.get(var.get("idType", ""), VariableRole.INPUT),
                assignment=var.get("assignment") or None,
                copilot_assignment=var.get("copilotAssignment") or None,
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


def _sub_formula_to_requirement_dict(sub: SubFormula, parent: FretRequirement, project: str, declared_names: set[str]) -> dict:
    """Builds a FRET-requirement-shaped dict for a split's sub-formula, ready to append to a
    project export's "requirements" array -- round-trips cleanly back through import_fret_file
    since it fills every field that function reads (pt/ptExpanded and ft/ftExpanded/
    ftInfAUExpanded all get the same already-resolved value, which is fine: the distinction
    between those fields only mattered for FRET's own raw export, not for formulas this project
    generated itself)."""
    return {
        "reqid": sub.id,
        "parent_reqid": parent.reqid,
        "project": project,
        "fulltext": f"(LLM split of {parent.reqid}) {parent.fulltext}".strip(),
        "is_assumption": parent.is_assumption,
        "semantics": {
            "pt": sub.pt_formula,
            "ptExpanded": sub.pt_formula,
            "ft": sub.ft_formula,
            "ftExpanded": sub.ft_formula,
            "ftInfAUExpanded": sub.ft_formula,
            "variables": _referenced_variable_names(sub, declared_names),
        },
    }


def append_sub_formulas_and_save(
    source_path: str | Path, sub_formulas: list[SubFormula], parent: FretRequirement, project: str,
    declared_names: set[str], output_path: str | Path, current_requirements: list[FretRequirement] = (),
) -> None:
    """Reads the FRET project export at `source_path`, appends `sub_formulas` (a split's
    results) to its "requirements" array as entries parented to `parent`, and writes the result
    to `output_path` -- a new file. `source_path` is never modified, so the original FRET
    export this project was given always stays intact.

    `current_requirements` is the caller's current in-memory list (post any GUI edits, such as
    toggling `is_assumption`) -- its values are patched onto the matching existing entries before
    writing, so a toggle made before a split isn't silently lost when the split is saved; entries
    not present in `current_requirements` are written through unchanged."""
    source_path = Path(source_path)
    try:
        data = json.loads(source_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidFretFileError(f"Couldn't read '{source_path}' as JSON: {exc}") from exc

    is_assumption_by_reqid = {r.reqid: r.is_assumption for r in current_requirements}
    for req in data.get("requirements", []):
        if req.get("reqid") in is_assumption_by_reqid:
            req["is_assumption"] = is_assumption_by_reqid[req["reqid"]]

    new_entries = [_sub_formula_to_requirement_dict(sub, parent, project, declared_names) for sub in sub_formulas]
    data["requirements"] = list(data.get("requirements", [])) + new_entries

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))
