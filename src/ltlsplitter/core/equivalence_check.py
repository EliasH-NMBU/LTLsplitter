from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, replace
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


def _substitute_internal_variables(formula: str, variables: list[Variable]) -> str:
    """Replaces each Internal-role variable's bare name with its (parenthesized) defining
    expression -- confirmed by hand this matters, not a hypothetical gap: unlike nuXmv (which
    gets this right via a DEFINE), neither Spot nor SPIN have any model/DEFINE concept of their
    own, so without this they silently treated a derived variable (e.g. FRET's
    "dgt_3 := distance_to_target > 3") as an *independent* free proposition, decoupled from the
    real variable it comes from. That produced a false "not tautology" for the exact case
    `test_nuxmv_substitutes_internal_variable_via_define` already confirms nuXmv gets right:
    "(G dgt_3) <-> (G (distance_to_target > 3))" is a genuine tautology by dgt_3's own
    definition, but Spot/SPIN found a "counterexample" where they disagree -- impossible in
    reality, since dgt_3 can't actually take a value other than that comparison's.

    Internal variables are not confirmed, in any real FRET export seen so far, to be defined in
    terms of other Internal variables, but that's not ruled out either -- this repeats
    substitution until no further Internal variable name remains in the formula (bounded by the
    number of Internal variables, enough for any acyclic dependency chain) rather than assuming
    one pass is always enough."""
    internal_by_name = {v.name: v.assignment for v in variables if v.role == VariableRole.INTERNAL and v.assignment}
    if not internal_by_name:
        return formula

    for _ in range(len(internal_by_name) + 1):
        changed = False
        for name, assignment in internal_by_name.items():
            pattern = re.compile(rf"\b{re.escape(name)}\b")
            if pattern.search(formula):
                formula = pattern.sub(lambda _m, expr=assignment: f"({expr})", formula)
                changed = True
        if not changed:
            break
    return formula


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
    status = {"tautology": "pass", "not_tautology": "fail"}.get(check.status, "error")
    return ToolCheckResult(tool=tool, passed=status == "pass", details=check.details, status=status)


def _as_nondegeneracy_result(tool: str, check: _TautologyCheck) -> ToolCheckResult:
    """Non-degenerate means the sub-formula is NOT equivalent to the original."""
    status = {"not_tautology": "pass", "tautology": "fail"}.get(check.status, "error")
    return ToolCheckResult(tool=tool, passed=status == "pass", details=check.details, status=status)


# -- nuXmv: both pt and ft use H/G-style LTL nuXmv understands natively -----------------------

_TYPE_HINT = (
    "If these are really booleans, the file declares them with a numeric dataType (or none, in "
    "an older export of this project) -- fix the dataType in the FRET file and re-import."
)
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

    try:
        output = _run_nuxmv_check(nuxmv, _nuxmv_model(variables, formula))
    except subprocess.TimeoutExpired:
        return _TautologyCheck("error", f"nuXmv timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s.")
    match = _NUXMV_TAUTOLOGY_RE.search(output)
    if not match:
        type_error = re.search(r"illegal operand types? of [^\n]*", output)
        if type_error:
            return _TautologyCheck(
                "error",
                f"nuXmv rejected the variable types ({type_error.group(0).strip()}): a variable "
                f"used as a truth value is declared as a number. {_TYPE_HINT}",
            )
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

    formula = _substitute_internal_variables(formula, variables)
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
            "literal\"/\"variable OP variable\" comparisons -- couldn't handle: "
            f"{', '.join(leftover)}. {_TYPE_HINT}",
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
    try:
        result = subprocess.run(
            [str(ltlfilt), "--equivalent-to=1", "-f", quoted_formula, "-q"],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return _TautologyCheck("error", f"ltlfilt timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s.")

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

    typed_names = {v.name for v in free_vars if v.type != VariableType.BOOL}
    comparisons, _ = extract_typed_comparisons(formula, typed_names)

    literal_values_by_var: dict[str, set[str]] = {name: set() for name in typed_names}
    links: dict[str, set[str]] = {name: set() for name in typed_names}
    for comparison in comparisons:
        if comparison.other_variable is None:
            literal = re.search(r"-?\d+(?:\.\d+)?$", comparison.text).group(0)
            literal_values_by_var[comparison.variable].add(literal)
        else:
            links[comparison.variable].add(comparison.other_variable)
            links[comparison.other_variable].add(comparison.variable)

    # Two typed variables compared directly to each other ("y = mode", not "mode = 0") must
    # each explore every value the OTHER side is known to take too -- otherwise one side's
    # domain can stay too narrow to ever reach the values needed to test the comparison in both
    # directions, which would make SPIN's search incomplete (risking a false "tautology" from a
    # missed counterexample) rather than merely imprecise. Propagated to a fixed point since a
    # chain of comparisons (e.g. "y = mode" and "mode = z") must widen every linked variable
    # alike, not just the two in any one comparison.
    changed = True
    while changed:
        changed = False
        for name, linked in links.items():
            for other in linked:
                if not literal_values_by_var[other] <= literal_values_by_var[name]:
                    literal_values_by_var[name] |= literal_values_by_var[other]
                    changed = True

    decl_lines: list[str] = []
    branch_lines: list[str] = []
    for var in free_vars:
        literal_values = sorted(literal_values_by_var.get(var.name, ()))
        decl, branch = _promela_var_declaration(var, literal_values, start_first)
        decl_lines.append(decl)
        branch_lines.append(f"    {branch}")

    decls = "\n".join(decl_lines) or "bool _unused;"
    step = f"atomic {{\n" + "\n".join(branch_lines) + "\n    }" if branch_lines else "skip"
    return f"{decls}\n\nactive proctype system() {{\n  do\n  :: {step}\n  od\n}}\n"


def _spin_safe_names(formula: str, variables: list[Variable]) -> tuple[str, list[Variable]]:
    """SPIN's LTL parser only takes propositions starting with a lowercase letter ("expected
    predicate, saw 'I'" for IMUFail -- found on UseCase6), so capitalised variables are renamed
    to a lowercase-prefixed alias, consistently in the formula and in the generated model."""
    declared = {v.name for v in variables}
    renames = {name: f"v_{name}" for name in declared if not name[:1].islower()}
    taken = declared | set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", formula))
    for name in list(renames):
        while renames[name] in taken:
            renames[name] = "v_" + renames[name]
    if not renames:
        return formula, variables
    formula = re.sub(
        r"\b[A-Za-z_][A-Za-z0-9_]*\b", lambda m: renames.get(m.group(0), m.group(0)), formula
    )
    variables = [replace(v, name=renames.get(v.name, v.name)) for v in variables]
    return formula, variables


def _check_tautology_spin(formula: str, variables: list[Variable]) -> _TautologyCheck:
    if _is_trivial_tautology(formula):
        return _TautologyCheck("tautology")

    formula = _substitute_internal_variables(formula, variables)
    if _is_trivial_tautology(formula):
        return _TautologyCheck("tautology")
    formula, variables = _spin_safe_names(formula, variables)

    typed_names = {v.name for v in variables if v.type != VariableType.BOOL}
    comparisons, leftover = extract_typed_comparisons(formula, typed_names)
    if leftover:
        return _TautologyCheck(
            "error",
            "SPIN's free model here only supports purely-boolean atomic propositions or simple "
            "\"variable OP literal\"/\"variable OP variable\" comparisons -- couldn't handle: "
            f"{', '.join(leftover)}. {_TYPE_HINT}",
        )

    try:
        spin = _find_binary("SPIN_PATH", "spin")
    except ToolNotFoundError as exc:
        return _TautologyCheck("error", str(exc))
    if not shutil.which("gcc") and not shutil.which("cc"):
        return _TautologyCheck("error", "SPIN check needs a C compiler (gcc/cc) to build pan.")

    # Confirmed by hand, not hypothetical: `spin -f` itself (translating the formula into a
    # never claim -- no model, no state-space exploration yet) can blow up and never return for
    # a biconditional between two differently-shaped-but-equivalent formulas (e.g. one big
    # conjunction on one side, the same conjuncts each separately wrapped in their own "G" on
    # the other -- exactly what comparing a split's conjunction against the original produces).
    # Each side alone translates instantly; it's specifically negating their biconditional that
    # can hit this translator's worst case. Caught here (and around every other spin/pan
    # subprocess call below) so a timeout becomes just *this tool's* "error" result, the same as
    # a missing binary -- without this, an uncaught TimeoutExpired propagates out of
    # validate_decomposition entirely and discards nuXmv/Spot's results too, not just SPIN's.
    # The model's declared starting values are a fixed, dummy state 0 -- the never claim is
    # evaluated against it before any nondeterministic step -- so the formula is checked from
    # step 1 on ("X"), where every valuation is reachable. Without this, step 0 was only ever
    # all-true or all-false, which missed counterexamples that live at the first step (found on
    # UseCase6: SPIN called "u -> F d" plus the edge case equivalent to the edge case alone,
    # because "u true, d false at step 0" was never explored).
    try:
        never_claim = subprocess.run(
            [str(spin), "-f", _to_spin_syntax(f"!(X ({formula}))")],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return _TautologyCheck("error", f"spin -f timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s translating the formula to a never claim.")
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
    # spin -f simplifies an unsatisfiable negation to a claim whose only guard is "false" --
    # the formula is a tautology. Checked here because pan then (correctly) explores nothing,
    # which the depth check below would otherwise report as "no verdict".
    guards = re.findall(r"::\s*(?:atomic\s*\{\s*)?\(([^)]*)\)", never_claim_text)
    if guards and all(g.strip() == "false" for g in guards):
        return _TautologyCheck("tautology")
    for comparison in comparisons:
        # only a bare "=" (equality) needs upgrading -- "!=", "<=", ">=" are already valid
        # Promela as-is and must be left alone.
        promela_text = re.sub(r"(?<![!<>=])=(?!=)", "==", comparison.text)
        never_claim_text = never_claim_text.replace(comparison.text, promela_text)

    # Promela has no "xor" keyword either -- confirmed by hand, not hypothetical: this project's
    # formula syntax allows "A xor B" as a boolean connective (e.g. mutual-exclusivity clauses
    # like "(mode = 0) xor (mode = 1)"), and spin -f carries it through verbatim into the never
    # claim's guards the same way it does with comparisons, so spin -a rejects the resulting
    # text as a syntax error ("near 'xor'") when compiling it as real Promela source. "A xor B"
    # and "A != B" are the same boolean function for boolean-valued A/B, which both sides always
    # are here (xor only ever appears between comparison/boolean sub-expressions in this
    # project's formulas, never between raw integers), and "!=" is valid Promela.
    never_claim_text = re.sub(r"\bxor\b", "!=", never_claim_text)

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

            try:
                gen = subprocess.run(
                    [str(spin), "-a", model_path.name],
                    capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
                    stdin=subprocess.DEVNULL, cwd=tmp_path,
                )
            except subprocess.TimeoutExpired:
                return _TautologyCheck("error", f"spin -a timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s.")
            if gen.returncode != 0:
                output = (gen.stdout + gen.stderr).strip()
                return _TautologyCheck("error", f"spin -a failed:\n{output[-1500:]}")

            try:
                build = subprocess.run(
                    [compiler, "-O2", "-o", "pan", "pan.c"],
                    capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
                    stdin=subprocess.DEVNULL, cwd=tmp_path,
                )
            except subprocess.TimeoutExpired:
                return _TautologyCheck("error", f"pan.c build timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s.")
            if build.returncode != 0:
                output = (build.stdout + build.stderr).strip()
                return _TautologyCheck("error", f"pan.c build failed:\n{output[-1500:]}")

            try:
                run = subprocess.run(
                    [str(tmp_path / "pan"), "-a"],
                    capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
                    stdin=subprocess.DEVNULL, cwd=tmp_path,
                )
            except subprocess.TimeoutExpired:
                return _TautologyCheck("error", f"pan state-space search timed out after {_SUBPROCESS_TIMEOUT_SECONDS}s.")
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


def _at_every_step(pt_formula: str) -> str:
    """A past-time formula is a property of each trace prefix -- the runtime monitor evaluates
    it at every step -- but an LTLSPEC is only evaluated at the initial state. Checking a pt
    biconditional bare therefore only compared the two sides at step 0, where e.g. "the trigger
    held at the first step" and "the trigger just rose" can't be told apart (found on UseCase6:
    nuXmv called UC6_R_16.2 alone equivalent to all of UC6_R_16). G makes it every step. The
    trivial-tautology fast path still sees through it via _is_trivial_tautology's own check on
    the unwrapped text."""
    if _is_trivial_tautology(pt_formula):
        return pt_formula
    return f"G ({pt_formula})"


def _check_all_tools(pt_formula: str, ft_formula: str, variables: list[Variable]) -> list[tuple[str, _TautologyCheck]]:
    # Only nuXmv supports past-time operators (H/O/S/Y) -- confirmed against the real binaries,
    # not assumed. Spot and SPIN both only parse future-time LTL, so they validate the ft form.
    # See the README's "which LTL form" note. (Each _check_tautology_* function already fast-
    # paths an exact self-comparison via _is_trivial_tautology on its own -- not repeated here
    # -- so a direct call to one of them gets the same protection as going through here.)
    return [
        ("nuXmv", _check_tautology_nuxmv(_at_every_step(pt_formula), variables)),
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
