from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ltlsplitter.core.models import DecompositionValidation, SubFormula, ToolCheckResult, Variable, VariableRole
from ltlsplitter.core.realizability import ToolNotFoundError, _find_binary, _nuxmv_env, _smv_var_type

_SUBPROCESS_TIMEOUT_SECONDS = 120

# -- shared helpers -----------------------------------------------------------------------


def _conjunction(formulas: list[str]) -> str:
    return " & ".join(f"({f})" for f in formulas)


def _biconditional(original: str, other: str) -> str:
    return f"({original}) <-> ({other})"


@dataclass
class _TautologyCheck:
    """A tool's verdict on whether a formula is a tautology. "error" (tool missing, crashed,
    or gave unparseable output) is kept distinct from "not_tautology" so a broken/missing tool
    can never be read as a logical result in either direction."""

    status: Literal["tautology", "not_tautology", "error"]
    details: str = ""


def _as_equivalence_result(tool: str, check: _TautologyCheck) -> ToolCheckResult:
    return ToolCheckResult(tool=tool, passed=check.status == "tautology", details=check.details)


def _as_nondegeneracy_result(tool: str, check: _TautologyCheck) -> ToolCheckResult:
    """Non-degenerate means the sub-formula is NOT equivalent to the original."""
    return ToolCheckResult(tool=tool, passed=check.status == "not_tautology", details=check.details)


# -- nuXmv: both pt and ft use H/G-style LTL nuXmv understands natively -----------------------

_NUXMV_TAUTOLOGY_RE = re.compile(r"-- specification .* is (true|false)")


def _nuxmv_model(variables: list[Variable], ltlspec: str) -> str:
    lines = ["MODULE main", "VAR"]
    free_vars = [v for v in variables if v.role != VariableRole.INTERNAL]
    if free_vars:
        for var in free_vars:
            lines.append(f"  {var.name} : {_smv_var_type(var)};")
    else:
        lines.append("  _unused : boolean;")  # nuXmv requires at least one declared variable
    internal_vars = [v for v in variables if v.role == VariableRole.INTERNAL and v.assignment]
    if internal_vars:
        lines.append("DEFINE")
        for var in internal_vars:
            lines.append(f"  {var.name} := {var.assignment};")
    lines.append(f"LTLSPEC {ltlspec};")
    return "\n".join(lines) + "\n"


def _run_nuxmv_check(nuxmv: Path, smv_text: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "model.smv"
        model_path.write_text(smv_text)
        commands_path = Path(tmp) / "commands.txt"
        commands_path.write_text("go\ncheck_ltlspec\nquit\n")
        result = subprocess.run(
            [str(nuxmv), "-source", str(commands_path), str(model_path)],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL, env=_nuxmv_env(),
        )
        return result.stdout + result.stderr


def _check_tautology_nuxmv(formula: str, variables: list[Variable]) -> _TautologyCheck:
    try:
        nuxmv = _find_binary("NUXMV_PATH", "nuXmv")
    except ToolNotFoundError as exc:
        return _TautologyCheck("error", str(exc))

    output = _run_nuxmv_check(nuxmv, _nuxmv_model(variables, formula))
    match = _NUXMV_TAUTOLOGY_RE.search(output)
    if not match:
        return _TautologyCheck("error", f"Couldn't parse nuXmv output:\n{output[-1500:]}")
    if match.group(1) == "true":
        return _TautologyCheck("tautology")
    return _TautologyCheck("not_tautology", output[-1500:])


# -- Spot: ft forms only -- confirmed against the real binary that Spot's LTL parser does NOT
# support past-time operators (H/O/S/Y all fail to parse: "syntax error, unexpected opening
# parenthesis") -- it's a future-LTL/omega-automata tool, not a PLTL one. ----------------------


def _check_tautology_spot(formula: str, variables: list[Variable]) -> _TautologyCheck:  # noqa: ARG001
    try:
        ltlfilt = _find_binary("SPOT_LTLFILT_PATH", "ltlfilt")
    except ToolNotFoundError as exc:
        return _TautologyCheck("error", str(exc))

    # --equivalent-to takes an inline FORMULA (confirmed against the real binary -- despite most
    # of Spot's other formula-reference options taking a FILENAME, this one doesn't), so
    # formula is a tautology iff it's equivalent to the constant "1" (true).
    result = subprocess.run(
        [str(ltlfilt), "--equivalent-to=1", "-f", formula, "-q"],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
    )

    if result.returncode not in (0, 1):
        output = (result.stdout + result.stderr).strip()
        return _TautologyCheck("error", f"ltlfilt failed:\n{output[-1500:]}")
    # ltlfilt -q prints nothing; exit 0 means the input formula survived the filter (i.e. is
    # equivalent to "1"/true), exit 1 means it didn't.
    if result.returncode == 0:
        return _TautologyCheck("tautology")
    return _TautologyCheck("not_tautology", "Not equivalent to a tautology (ltlfilt).")


# -- SPIN: ft forms only -- `spin -f` only accepts pure future LTL, no past operators ----------
#
# SPIN's LTL parser (confirmed against the real binary) uses symbolic "[]"/"<>" for
# always/eventually rather than the keywords "G"/"F" -- X, U, R, V, !, &, |, ->, <-> all match
# our formulas' syntax already and need no translation.

_SPIN_ALWAYS_RE = re.compile(r"\bG\b")
_SPIN_EVENTUALLY_RE = re.compile(r"\bF\b")


def _to_spin_syntax(formula: str) -> str:
    return _SPIN_EVENTUALLY_RE.sub("<>", _SPIN_ALWAYS_RE.sub("[]", formula))


def _promela_model(variables: list[Variable]) -> str:
    """A free-running model: every (non-internal) proposition is reassigned nondeterministically
    forever, so the never claim sees every possible truth-value sequence. All variables are
    reassigned together in one atomic{} step -- not one at a time -- so every state is a fresh,
    independent, complete valuation (matching the free Kripke structure nuXmv/Spot use here),
    rather than only ever differing from the previous state in a single variable."""
    free_vars = [v for v in variables if v.role != VariableRole.INTERNAL]
    decls = "\n".join(f"bool {v.name};" for v in free_vars) or "bool _unused;"
    if free_vars:
        assignments = "\n".join(f"    if :: {v.name} = true :: {v.name} = false fi;" for v in free_vars)
        step = f"atomic {{\n{assignments}\n    }}"
    else:
        step = "skip"
    return f"{decls}\n\nactive proctype system() {{\n  do\n  :: {step}\n  od\n}}\n"


def _check_tautology_spin(formula: str, variables: list[Variable]) -> _TautologyCheck:
    try:
        spin = _find_binary("SPIN_PATH", "spin")
    except ToolNotFoundError as exc:
        return _TautologyCheck("error", str(exc))
    if not shutil.which("gcc") and not shutil.which("cc"):
        return _TautologyCheck("error", "SPIN check needs a C compiler (gcc/cc) to build pan.")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        never_claim = subprocess.run(
            [str(spin), "-f", _to_spin_syntax(f"!({formula})")],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
        if never_claim.returncode != 0 or not never_claim.stdout.strip():
            output = (never_claim.stdout + never_claim.stderr).strip()
            return _TautologyCheck("error", f"Couldn't parse formula with spin -f:\n{output[-1500:]}")

        model_path = tmp_path / "model.pml"
        model_path.write_text(_promela_model(variables) + "\n" + never_claim.stdout)

        gen = subprocess.run(
            [str(spin), "-a", model_path.name],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL, cwd=tmp_path,
        )
        if gen.returncode != 0:
            output = (gen.stdout + gen.stderr).strip()
            return _TautologyCheck("error", f"spin -a failed:\n{output[-1500:]}")

        compiler = shutil.which("gcc") or shutil.which("cc")
        build = subprocess.run(
            [compiler, "-O2", "-o", "pan", "pan.c"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL, cwd=tmp_path,
        )
        if build.returncode != 0:
            output = (build.stdout + build.stderr).strip()
            return _TautologyCheck("error", f"pan.c build failed:\n{output[-1500:]}")

        run = subprocess.run(
            [str(tmp_path / "pan"), "-a"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL, cwd=tmp_path,
        )
        output = run.stdout + run.stderr

    if "errors: 0" in output:
        return _TautologyCheck("tautology")
    if "errors:" in output:
        return _TautologyCheck("not_tautology", output[-1500:])
    return _TautologyCheck("error", f"Couldn't parse pan output:\n{output[-1500:]}")


# -- orchestration --------------------------------------------------------------------------


def _check_all_tools(pt_formula: str, ft_formula: str, variables: list[Variable]) -> list[tuple[str, _TautologyCheck]]:
    # Only nuXmv supports past-time operators (H/O/S/Y) -- confirmed against the real binaries,
    # not assumed. Spot and SPIN both only parse future-time LTL, so they validate the ft form.
    # See the README's "which LTL form" note.
    return [
        ("nuXmv", _check_tautology_nuxmv(pt_formula, variables)),
        ("Spot", _check_tautology_spot(ft_formula, variables)),
        ("SPIN", _check_tautology_spin(ft_formula, variables)),
    ]


def validate_decomposition(
    original_pt: str,
    original_ft: str,
    sub_formulas: list[SubFormula],
    variables: list[Variable],
) -> DecompositionValidation:
    """Checks, with nuXmv/Spot/SPIN, that the sub-formulas' conjunction is equivalent to the
    original formula, and that no single sub-formula is -- by itself -- already equivalent to
    the whole original (which would mean it wasn't a genuine split)."""
    conjunction_pt = _biconditional(original_pt, _conjunction([s.pt_formula for s in sub_formulas]))
    conjunction_ft = _biconditional(original_ft, _conjunction([s.ft_formula for s in sub_formulas]))
    equivalence = [
        _as_equivalence_result(tool, check) for tool, check in _check_all_tools(conjunction_pt, conjunction_ft, variables)
    ]

    nondegeneracy: dict[str, list[ToolCheckResult]] = {}
    if len(sub_formulas) > 1:
        for sub in sub_formulas:
            sub_pt = _biconditional(original_pt, sub.pt_formula)
            sub_ft = _biconditional(original_ft, sub.ft_formula)
            nondegeneracy[sub.id] = [
                _as_nondegeneracy_result(tool, check) for tool, check in _check_all_tools(sub_pt, sub_ft, variables)
            ]

    return DecompositionValidation(equivalence=equivalence, nondegeneracy=nondegeneracy)
