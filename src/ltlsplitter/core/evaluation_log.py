"""Evaluation data for the splitting methodology: one folder per use case under a data root,
holding the session's saved split file and `decomposition_evaluations.csv`, which gets one row
appended every time a decomposition is validated on page 2.

Complexity is core/complexity.py's score (operators + 0.5 x distinct variables), computed
separately for the ptLTL and ftLTL forms since they differ in size for the same obligation.
"Delta" is always decomposition minus original, so a positive delta total is the overhead a
split adds and a negative delta mean is how much smaller the average part is."""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from statistics import mean

from ltlsplitter.core.complexity import formula_complexity
from ltlsplitter.core.models import DecompositionValidation, FretRequirement, SubFormula, ToolCheckResult

EVALUATION_FILE_NAME = "decomposition_evaluations.csv"
_TOOLS = ("nuXmv", "Spot", "SPIN")

COLUMNS = (
    "timestamp",
    "use_case",
    "requirement_id",
    "sub_requirement_count",
    "sub_requirement_ids",
    "original_complexity_pt",
    "original_complexity_ft",
    "decomp_total_complexity_pt",
    "decomp_total_complexity_ft",
    "decomp_mean_complexity_pt",
    "decomp_mean_complexity_ft",
    "decomp_max_complexity_pt",
    "decomp_max_complexity_ft",
    "delta_total_complexity_pt",
    "delta_total_complexity_ft",
    "delta_mean_complexity_pt",
    "delta_mean_complexity_ft",
    "soundness_nuxmv",
    "soundness_spot",
    "soundness_spin",
    "semantic_spread_nuxmv",
    "semantic_spread_spot",
    "semantic_spread_spin",
    "all_checks_passed",
    "source_file",
)


def use_case_folder_name(project: str, import_path: str | Path | None = None) -> str:
    """A filesystem-safe folder name for a use case: the FRET project name (kept by every file
    this project saves, so re-importing a saved split lands in the same folder), or the
    imported file's name when the project has none (e.g. an .smv import)."""
    name = project.strip() or (Path(import_path).stem if import_path else "") or "unnamed_use_case"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name or "unnamed_use_case"


def ensure_use_case_folder(data_root: str | Path, project: str, import_path: str | Path | None = None) -> Path:
    folder = Path(data_root) / use_case_folder_name(project, import_path)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _round(value: float) -> float:
    return round(value, 3)


def _complexity_columns(original: str, parts: list[str], suffix: str, declared: set[str] | None) -> dict:
    keys = ("original", "decomp_total", "decomp_mean", "decomp_max", "delta_total", "delta_mean")
    if not original or not parts or not all(parts):
        return {f"{k}_complexity_{suffix}": "" for k in keys}  # e.g. an .smv import with only one form
    original_score = formula_complexity(original, declared).score
    scores = [formula_complexity(p, declared).score for p in parts]
    total, avg = sum(scores), mean(scores)
    return {
        f"original_complexity_{suffix}": _round(original_score),
        f"decomp_total_complexity_{suffix}": _round(total),
        f"decomp_mean_complexity_{suffix}": _round(avg),
        f"decomp_max_complexity_{suffix}": _round(max(scores)),
        f"delta_total_complexity_{suffix}": _round(total - original_score),
        f"delta_mean_complexity_{suffix}": _round(avg - original_score),
    }


def _status(result: ToolCheckResult | None) -> str:
    if result is None:
        return "NOT_RUN"
    return result.status.upper() if result.status else ("PASS" if result.passed else "FAIL")


def _tool_result(results: list[ToolCheckResult], tool: str) -> ToolCheckResult | None:
    return next((r for r in results if r.tool == tool), None)


def _spread_status(validation: DecompositionValidation, tool: str) -> str:
    """Semantic spread (non-degeneracy) for one tool over every part: PASS only if no part
    alone is the whole original; FAIL names the parts that are; ERROR if the tool couldn't
    decide for some part (and none failed)."""
    if not validation.nondegeneracy:
        return "NOT_RUN"
    failed, errored = [], []
    for sub_id, results in validation.nondegeneracy.items():
        status = _status(_tool_result(results, tool))
        if status == "FAIL":
            failed.append(sub_id)
        elif status != "PASS":
            errored.append(sub_id)
    if failed:
        return "FAIL (" + " ".join(failed) + ")"
    if errored:
        return "ERROR (" + " ".join(errored) + ")"
    return "PASS"


def evaluation_row(
    use_case: str,
    requirement: FretRequirement,
    sub_formulas: list[SubFormula],
    validation: DecompositionValidation,
    declared_names: set[str] | None = None,
    source_file: str = "",
    timestamp: datetime | None = None,
) -> dict:
    row = {
        "timestamp": (timestamp or datetime.now()).isoformat(timespec="seconds"),
        "use_case": use_case,
        "requirement_id": requirement.reqid.strip(),
        "sub_requirement_count": len(sub_formulas),
        "sub_requirement_ids": " ".join(s.id.strip() for s in sub_formulas),
        "all_checks_passed": validation.all_passed,
        "source_file": source_file,
    }
    row |= _complexity_columns(requirement.pt_formula, [s.pt_formula for s in sub_formulas], "pt", declared_names)
    row |= _complexity_columns(requirement.ft_formula, [s.ft_formula for s in sub_formulas], "ft", declared_names)
    for tool in _TOOLS:
        row[f"soundness_{tool.lower()}"] = _status(_tool_result(validation.equivalence, tool))
        row[f"semantic_spread_{tool.lower()}"] = _spread_status(validation, tool)
    return row


def append_evaluation(folder: str | Path, row: dict) -> Path:
    """Appends `row` to the use case's CSV, writing the header first if the file is new."""
    path = Path(folder) / EVALUATION_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in COLUMNS})
    return path
