from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from ltlsplitter.core.models import RealizabilityResult, Variable, VariableRole, VariableType
from ltlsplitter.core.realizability import ToolNotFoundError, _find_binary

_SUBPROCESS_TIMEOUT_SECONDS = 120

_LUSTRE_TYPES = {
    VariableType.BOOL: "bool",
    VariableType.INT: "int",
    VariableType.FLOAT: "real",
    # Lustre enums need a declared `type T = enum {...}`; no FRET export seen so far exercises
    # ENUM, so (matching the same simplification ogma.py already makes) it's treated as an
    # index instead of adding an untested feature.
    VariableType.ENUM: "int",
}


def _translate_propositional(expr: str) -> str:
    """Translates our SMV-style propositional syntax into a Lustre boolean expression.
    "<->" must be handled before "->" (which is a substring of it) -- unlike LTL, Lustre's "->"
    is the temporal "init"/followed-by operator, not implication, so getting this order wrong
    would silently produce a syntactically-valid but semantically-wrong Lustre expression."""
    expr = expr.replace("<->", "=")
    expr = expr.replace("->", "=>")
    expr = expr.replace("&", " and ")
    expr = expr.replace("|", " or ")
    expr = expr.replace("!", " not ")
    return expr


def _strip_top_level_h(formula: str) -> str | None:
    """FRET's past-time (pt) formulas always take the shape "(H (...))" -- a single H wrapping
    an otherwise-propositional body (the same "single temporal operator" shape Ogma's own
    parser requires, confirmed against real exports). Kind2 has no built-in H/historically
    operator (confirmed against the real binary -- it's plain Lustre, not FRET's older CoCoSpec
    dialect), so H is compiled by hand into a ghost variable recurring on `pre`. Returns the
    inner propositional body, or None if the formula doesn't match that single-top-level-H
    shape (nested/multiple H's aren't supported here).

    Uses a balanced-parenthesis scan rather than a regex: a naive greedy regex matching an
    opening "(H (" and a closing "))" would wrongly accept "(H (a)) & (H (b))" as a single
    H-wrapped term (it merely starts and ends with the right characters) instead of correctly
    rejecting it as two separate top-level terms -- confirmed by a test that caught exactly
    this."""
    text = formula.strip()
    if not text.startswith("("):
        return None
    rest = text[1:].lstrip()
    if not rest.startswith("H"):
        return None
    rest = rest[1:].lstrip()
    if not rest.startswith("("):
        return None

    depth = 0
    for i, ch in enumerate(rest):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                body = rest[1:i]
                trailing = rest[i + 1:].strip()
                return body if trailing == ")" else None
    return None


def _lustre_type(var: Variable) -> str:
    return _LUSTRE_TYPES[var.type]


def _ghost_var_declarations(internal_vars: list[Variable]) -> list[str]:
    return [
        f"  var {var.name}: {_lustre_type(var)} = {_translate_propositional(var.assignment)};"
        for var in internal_vars
        if var.assignment
    ]


def _build_lustre_contract(pt_formulas: list[str], variables: list[Variable]) -> tuple[str, int, list[str]]:
    """Returns (lustre source, number of formulas successfully translated into guarantees,
    formulas that didn't match the supported "(H (...))" shape and were skipped -- so the
    caller can report that honestly instead of silently dropping them from the check)."""
    inputs = [v for v in variables if v.role == VariableRole.INPUT]
    outputs = [v for v in variables if v.role == VariableRole.OUTPUT]
    internal = [v for v in variables if v.role == VariableRole.INTERNAL]

    history_vars: list[str] = []
    guarantees: list[str] = []
    skipped: list[str] = []
    for i, formula in enumerate(pt_formulas):
        body = _strip_top_level_h(formula)
        if body is None:
            skipped.append(formula)
            continue
        ghost = f"_h{i}"
        history_vars.append(f"  var {ghost}: bool = ({_translate_propositional(body)}) and (true -> pre {ghost});")
        guarantees.append(ghost)

    in_params = "; ".join(f"{v.name}: {_lustre_type(v)}" for v in inputs)
    out_params = "; ".join(f"{v.name}: {_lustre_type(v)}" for v in outputs) or "_unused: bool"
    signature = f"node imported main({in_params}) returns ({out_params});"

    contract_body = _ghost_var_declarations(internal) + history_vars + [f"  guarantee {g};" for g in guarantees]
    lustre = signature + "\n(*@contract\n" + "\n".join(contract_body) + "\n*)\n"
    return lustre, len(guarantees), skipped


def _context_realizability(events: list[dict], context: str) -> dict | None:
    """Kind2's JSON output is a flat, time-ordered event stream -- "realizabilityCheck" events
    aren't nested under their "analysisStart", so the context ("contract" realizability itself
    vs. "environment", a separate secondary check on whether the assumptions are satisfiable)
    has to be tracked positionally while scanning."""
    current_context = None
    for event in events:
        object_type = event.get("objectType")
        if object_type == "analysisStart":
            current_context = event.get("context")
        elif object_type == "realizabilityCheck" and current_context == context:
            return event
    return None


def _format_deadlock(event: dict) -> str:
    trace = event.get("deadlockingTrace") or []
    if not trace:
        return ""
    values = []
    for stream in trace[0].get("streams", []):
        first_value = stream.get("instantValues", [[None, None]])[0]
        values.append(f"{stream['name']}={first_value[1]}")
    return "Deadlocking trace: " + ", ".join(values)


def check_realizability_kind2(pt_formulas: list[str], variables: list[Variable]) -> RealizabilityResult:
    """Checks realizability via Kind2's contract-realizability analysis (`--enable CONTRACTCK`)
    -- an SMT/k-induction-based alternative to Strix's game-synthesis approach, and (unlike
    Strix) one that understands typed/arithmetic FRET variables natively, since Lustre has real
    int/real types. Runs alongside Strix, not instead of it -- the two use different algorithms
    and checking both is a useful cross-check, not redundant."""
    if not pt_formulas:
        return RealizabilityResult(realizable=False, details="No formula to check.")

    try:
        kind2 = _find_binary("KIND2_PATH", "kind2")
    except ToolNotFoundError as exc:
        return RealizabilityResult(realizable=False, details=str(exc))

    lustre, guarantee_count, skipped = _build_lustre_contract(pt_formulas, variables)
    if guarantee_count == 0:
        return RealizabilityResult(
            realizable=False,
            details="None of the formulas are in the single-top-level-H shape this Kind2 "
            "integration supports (Kind2 has no built-in past-time operator) -- nothing to check.",
        )

    with tempfile.TemporaryDirectory() as tmp:
        lustre_path = Path(tmp) / "model.lus"
        lustre_path.write_text(lustre)
        result = subprocess.run(
            [str(kind2), "-json", "--enable", "CONTRACTCK", str(lustre_path)],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )

    try:
        events = json.loads(result.stdout)
    except json.JSONDecodeError:
        output = (result.stdout + result.stderr).strip()
        return RealizabilityResult(realizable=False, details=f"Couldn't parse kind2 output:\n{output[-1500:]}")

    event = _context_realizability(events, "contract")
    if event is None:
        output = (result.stdout + result.stderr).strip()
        return RealizabilityResult(realizable=False, details=f"kind2 produced no realizability verdict:\n{output[-1500:]}")

    skip_note = ""
    if skipped:
        skip_note = (
            f" ({len(skipped)} formula(s) skipped -- not in the supported (H (...)) shape, "
            "so this verdict only covers the rest.)"
        )

    verdict = event.get("result")
    if verdict == "realizable":
        return RealizabilityResult(realizable=True, details=skip_note.strip())
    if verdict == "unrealizable":
        return RealizabilityResult(realizable=False, details=(_format_deadlock(event) + skip_note).strip())
    return RealizabilityResult(realizable=False, details=f"kind2 couldn't determine realizability ({verdict}).{skip_note}")
