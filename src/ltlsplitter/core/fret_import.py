from __future__ import annotations

import json
from pathlib import Path

from ltlsplitter.core.models import FretImport, FretRequirement, Variable, VariableRole, VariableType

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
        requirements.append(
            FretRequirement(
                reqid=req["reqid"],
                fulltext=req.get("fulltext", ""),
                pt_formula=_pt_formula(semantics),
                ft_formula=_ft_formula(semantics),
                variable_names=list(semantics.get("variables", [])),
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
