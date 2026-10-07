from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ltlsplitter.core.models import (
    DecompositionValidation,
    SubFormula,
    ToolCheckResult,
    Variable,
    VariableRole,
    VariableType,
)
from ltlsplitter.core.realizability import ToolNotFoundError, _find_binary, _nuxmv_env, _smv_var_type
from ltlsplitter.core.typed_atoms import extract_typed_comparisons

_SUBPROCESS_TIMEOUT_SECONDS = 120

# -- shared helpers -----------------------------------------------------------------------


def _conjunction(formulas: list[str]) -> str:
    return " & ".join(f"({f})" for f in formulas)


def _biconditional(original: str, other: str) -> str:
    return f"({original}) <-> ({other})"


def _split_top_level_biconditional(formula: str) -> tuple[str, str] | None:
    """Finds the "<->" at paren-depth 0 (i.e. the one `_biconditional` itself inserted, not one
    possibly nested inside either side) and splits there."""
    depth = 0
    for i in range(len(formula) - 2):
        ch = formula[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and formula[i : i + 3] == "<->":
            return formula[:i], formula[i + 3 :]
    return None


def _strip_enclosing_parens(s: str) -> str:
    """Repeatedly removes one pair of parens wrapping the *entire* string (not just starting
    with "(" and ending with ")" -- that alone doesn't mean they match each other)."""
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        for i, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
        if i != len(s) - 1:  # the first "(" closes before the string ends -- not a full wrap
            break
        s = s[1:-1]
    return s


def _is_trivial_tautology(formula: str) -> bool:
    """Fast-path, no-tool-needed check: "(X) <-> (X)" (identical text, modulo redundant
    wrapping parens, on both sides of a top-level biconditional -- exactly the shape
    `_biconditional` builds, including when `_conjunction` adds one more wrapping layer around
    a lone sub-formula) is a tautology by construction, whatever X means. Cheap, 100% reliable,
    and -- unlike actually invoking a tool -- immune to SPIN's "stuck at the very first state"
    ambiguity (see `_check_tautology_spin`) for what's actually the single most common case
    this project hits: checking an unsplit formula against an exact copy of itself."""
    split = _split_top_level_biconditional(formula)
    if split is None:
        return False
    left, right = split
    # Collapse (not remove) whitespace -- removing it entirely risks merging adjacent tokens
    # (e.g. "G a" and "Ga" would otherwise compare equal, which isn't the intent here).
    normalize = lambda s: _strip_enclosing_parens(re.sub(r"\s+", " ", s.strip()))
    return normalize(left) == normalize(right)


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
    if _is_trivial_tautology(formula):
        return _TautologyCheck("tautology")
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


def _check_tautology_spot(formula: str, variables: list[Variable]) -> _TautologyCheck:
    if _is_trivial_tautology(formula):
        return _TautologyCheck("tautology")

    # Spot's LTL grammar only accepts bare-identifier atomic propositions -- "classifier = 1"
    # doesn't parse -- but it does accept a double-quoted string as one opaque atomic
    # proposition (confirmed against the real binary), so each "variable OP literal" comparison
    # is quoted in place rather than needing a separate fresh-name/substitution scheme: the
    # quoted text *is* the proposition name, and identical text is automatically the identical
    # proposition everywhere it recurs, with no bookkeeping needed.
    typed_names = {v.name for v in variables if v.type != VariableType.BOOL}
    comparisons, leftover = extract_typed_comparisons(formula, typed_names)
    if leftover:
        return _TautologyCheck(
            "error",
            "Spot only supports purely-boolean atomic propositions or simple \"variable OP "
            f"literal\" comparisons -- couldn't handle: {', '.join(leftover)}.",
        )
    quoted_formula = formula
    for comparison in comparisons:
        quoted_formula = quoted_formula.replace(comparison.text, f'"{comparison.text}"')

    try:
        ltlfilt = _find_binary("SPOT_LTLFILT_PATH", "ltlfilt")
    except ToolNotFoundError as exc:
        return _TautologyCheck("error", str(exc))

    # --equivalent-to takes an inline FORMULA (confirmed against the real binary -- despite most
    # of Spot's other formula-reference options taking a FILENAME, this one doesn't), so
    # formula is a tautology iff it's equivalent to the constant "1" (true).
    result = subprocess.run(
        [str(ltlfilt), "--equivalent-to=1", "-f", quoted_formula, "-q"],
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
# always/eventually rather than the keywords "G"/"F". X, U, R, V, !, ->, <-> all match our
# formulas' syntax already, but single "&"/"|" do NOT reliably work -- confirmed empirically
# that e.g. "([](a)) & ([](b))" is a parse error ("expected '&', saw ' '") while
# "([](a)) && ([](b))" parses fine; a bare "!(x & y)" happening to parse earlier was misleading
# (single "&" isn't consistently rejected, just unreliable once combined with a temporal
# operator like "[]" immediately to its left) -- "&&"/"||" are the tokens that actually work in
# general, so both get upgraded, not just translated case-by-case.

_SPIN_ALWAYS_RE = re.compile(r"\bG\b")
_SPIN_EVENTUALLY_RE = re.compile(r"\bF\b")
_SPIN_AND_RE = re.compile(r"(?<!&)&(?!&)")
_SPIN_OR_RE = re.compile(r"(?<!\|)\|(?!\|)")


def _to_spin_syntax(formula: str) -> str:
    formula = _SPIN_EVENTUALLY_RE.sub("<>", _SPIN_ALWAYS_RE.sub("[]", formula))
    formula = _SPIN_AND_RE.sub("&&", formula)
    return _SPIN_OR_RE.sub("||", formula)


def _promela_var_declaration(var: Variable, literal_values: list[str], start_first: bool) -> tuple[str, str]:
    """Returns (decl_line, if-branches) for one free variable. Typed variables are declared as
    a Promela `int` choosing nondeterministically among the literal values actually compared
    against it in this formula (confirmed SPIN's own LTL parser accepts "state = 1" as a
    literal atomic proposition, unlike Spot/Strix -- the bug this project had was never SPIN's
    parser, it was this function declaring every variable as `bool` regardless, silently
    collapsing a typed variable's real range to true/false), plus one sentinel value one past
    the largest seen, standing in for "anything else" -- sound without needing to know the
    variable's true domain, and keeps the explicit state space small rather than defaulting to
    an arbitrary wide range.

    `start_first` picks which end of the domain (or which boolean value) the declaration
    initializes to -- see `_check_tautology_spin` for why a single fixed choice isn't safe."""
    if var.type == VariableType.BOOL:
        first, second = ("true", "false") if start_first else ("false", "true")
        return f"bool {var.name} = {first};", f"if :: {var.name} = {first} :: {var.name} = {second} fi;"
    values = sorted({int(float(v)) for v in literal_values}) or [0]
    values.append(max(values) + 1)  # sentinel: "none of the compared-against values"
    initial = values[0] if start_first else values[-1]
    branches = " ".join(f":: {var.name} = {v}" for v in values)
    return f"int {var.name} = {initial};", f"if {branches} fi;"


def _promela_model(formula: str, variables: list[Variable], start_first: bool) -> str:
    """A free-running model: every proposition is reassigned nondeterministically forever, so
    the never claim sees every possible value sequence. All variables are reassigned together
    in one atomic{} step -- not one at a time -- so every state is a fresh, independent,
    complete valuation (matching the free Kripke structure nuXmv/Spot use here), rather than
    only ever differing from the previous state in a single variable."""
    referenced = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula))
    free_vars = [v for v in variables if v.name in referenced]

    decl_lines: list[str] = []
    branch_lines: list[str] = []
    for var in free_vars:
        literal_values = []
        if var.type != VariableType.BOOL:
            comparisons, _ = extract_typed_comparisons(formula, {var.name})
            literal_values = [re.search(r"-?\d+(?:\.\d+)?$", c.text).group(0) for c in comparisons]
        decl, branch = _promela_var_declaration(var, literal_values, start_first)
        decl_lines.append(decl)
        branch_lines.append(f"    {branch}")

    decls = "\n".join(decl_lines) or "bool _unused;"
    step = f"atomic {{\n" + "\n".join(branch_lines) + "\n    }" if branch_lines else "skip"
    return f"{decls}\n\nactive proctype system() {{\n  do\n  :: {step}\n  od\n}}\n"


def _check_tautology_spin(formula: str, variables: list[Variable]) -> _TautologyCheck:
    if _is_trivial_tautology(formula):
        return _TautologyCheck("tautology")

    typed_names = {v.name for v in variables if v.type != VariableType.BOOL}
    comparisons, leftover = extract_typed_comparisons(formula, typed_names)
    if leftover:
        return _TautologyCheck(
            "error",
            "SPIN's free model here only supports purely-boolean atomic propositions or simple "
            f"\"variable OP literal\" comparisons -- couldn't handle: {', '.join(leftover)}.",
        )

    try:
        spin = _find_binary("SPIN_PATH", "spin")
    except ToolNotFoundError as exc:
        return _TautologyCheck("error", str(exc))
    if not shutil.which("gcc") and not shutil.which("cc"):
        return _TautologyCheck("error", "SPIN check needs a C compiler (gcc/cc) to build pan.")

    never_claim = subprocess.run(
        [str(spin), "-f", _to_spin_syntax(f"!({formula})")],
        capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
    )
    if never_claim.returncode != 0 or not never_claim.stdout.strip():
        output = (never_claim.stdout + never_claim.stderr).strip()
        return _TautologyCheck("error", f"Couldn't parse formula with spin -f:\n{output[-1500:]}")

    # spin -f's never claim reuses each comparison verbatim (e.g. "(state = 1)") as a boolean
    # sub-expression inside compound guards ("!((state = 2)) && (state = 1) -> ..."), but
    # Promela's "=" is assignment, not equality, and is a syntax error inside a compound boolean
    # expression; only "==" is valid there. Rewrite just the known comparisons (found earlier,
    # before any substitution) to "==" in the never-claim text specifically -- this project's
    # own `_promela_model` output is untouched, since its "state = 1" lines are genuine
    # assignment statements, not comparisons.
    never_claim_text = never_claim.stdout
    for comparison in comparisons:
        # only a bare "=" (equality) needs upgrading -- "!=", "<=", ">=" are already valid
        # Promela as-is and must be left alone.
        promela_text = re.sub(r"(?<![!<>=])=(?!=)", "==", comparison.text)
        never_claim_text = never_claim_text.replace(comparison.text, promela_text)

    compiler = shutil.which("gcc") or shutil.which("cc")

    # Confirmed empirically (reproduced with a real formula from this project's own test
    # fixture, not hypothetical): the never claim's initial guards are evaluated against
    # whatever values the model's variables are *declared* with, and if that one fixed
    # combination doesn't happen to satisfy any of them, the search is permanently stuck at
    # depth 0 with zero transitions -- which `pan` reports as "errors: 0", silently
    # misread as "tautology" when really nothing was explored. No single fixed starting
    # combination is safe for every formula (a formula built from negated atoms needs the
    # opposite starting point from one built from bare atoms), so this tries two complementary
    # ones and only trusts a "tautology" verdict from a run that actually explored past the
    # initial state (depth > 0) -- a found counterexample is trusted immediately regardless,
    # since finding one is proof on its own, not something that needs "enough" exploration.
    stuck_runs = 0
    last_output = ""
    for start_first in (True, False):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            model_path = tmp_path / "model.pml"
            model_path.write_text(_promela_model(formula, variables, start_first) + "\n" + never_claim_text)

            gen = subprocess.run(
                [str(spin), "-a", model_path.name],
                capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
                stdin=subprocess.DEVNULL, cwd=tmp_path,
            )
            if gen.returncode != 0:
                output = (gen.stdout + gen.stderr).strip()
                return _TautologyCheck("error", f"spin -a failed:\n{output[-1500:]}")

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
            last_output = output

        errors_match = re.search(r"errors:\s*(\d+)", output)
        depth_match = re.search(r"depth reached (\d+)", output)
        if not errors_match or not depth_match:
            return _TautologyCheck("error", f"Couldn't parse pan output:\n{output[-1500:]}")

        if int(errors_match.group(1)) > 0:
            return _TautologyCheck("not_tautology", output[-1500:])
        if int(depth_match.group(1)) == 0:
            stuck_runs += 1
            continue
        return _TautologyCheck("tautology")  # explored (depth > 0) and found nothing: trustworthy

    return _TautologyCheck(
        "error",
        "SPIN's search got stuck at the very first state for every starting-value combination "
        "tried -- the never claim's initial guards didn't match, so nothing was actually "
        f"explored (not a real tautology verdict):\n{last_output[-1000:]}",
    )


# -- orchestration --------------------------------------------------------------------------


def _check_all_tools(pt_formula: str, ft_formula: str, variables: list[Variable]) -> list[tuple[str, _TautologyCheck]]:
    # Only nuXmv supports past-time operators (H/O/S/Y) -- confirmed against the real binaries,
    # not assumed. Spot and SPIN both only parse future-time LTL, so they validate the ft form.
    # See the README's "which LTL form" note. (Each _check_tautology_* function already fast-
    # paths an exact self-comparison via _is_trivial_tautology on its own -- not repeated here
    # -- so a direct call to one of them gets the same protection as going through here.)
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
