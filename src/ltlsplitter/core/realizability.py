from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ltlsplitter.core.models import (
    ConsistencyResult,
    RealizabilityResult,
    Specification,
    Variable,
    VariableRole,
    VariableType,
)
from ltlsplitter.core.typed_atoms import TypedComparison, extract_typed_comparisons

_LOCAL_BIN = Path.home() / ".local" / "bin"
_NUXMV_LIBSHIM = Path.home() / ".local" / "share" / "ltlsplitter-tools" / "nuxmv-libshim"

_SUBPROCESS_TIMEOUT_SECONDS = 120


class ToolNotFoundError(RuntimeError):
    """A required external tool (nuXmv or Strix) isn't installed or can't be located."""


def _find_binary(env_var: str, name: str) -> Path:
    """Locates an external tool binary: an explicit env var override first, then PATH,
    then the ~/.local/bin convention this project's docs use for manually-installed tools."""
    override = os.environ.get(env_var)
    if override:
        path = Path(override)
        if path.is_file():
            return path
        raise ToolNotFoundError(f"{env_var} is set to '{override}' but that file doesn't exist.")
    which = shutil.which(name)
    if which:
        return Path(which)
    candidate = _LOCAL_BIN / name
    if candidate.is_file():
        return candidate
    raise ToolNotFoundError(
        f"Couldn't find '{name}'. Install it (see README.md), then either add it to your PATH, "
        f"symlink it into ~/.local/bin, or set {env_var} to its full path."
    )


def _nuxmv_env() -> dict[str, str]:
    """nuXmv's official Linux binary needs libxml2.so.2/libicuuc.so.70/libicudata.so.70, which
    most distros no longer ship at that SONAME. If the ~/.local/share/ltlsplitter-tools shim
    described in README.md exists, point LD_LIBRARY_PATH at just those three libraries (not
    nuXmv's whole bundled lib/ dir, which also contains an old libc.so.6 that would break every
    subprocess nuXmv spawns if it shadowed the system one)."""
    env = dict(os.environ)
    if _NUXMV_LIBSHIM.is_dir():
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{_NUXMV_LIBSHIM}{os.pathsep}{existing}" if existing else str(_NUXMV_LIBSHIM)
    return env


def _smv_var_type(var: Variable) -> str:
    if var.type == VariableType.BOOL:
        return "boolean"
    if var.type == VariableType.ENUM:
        values = var.enum_values or ["undefined"]
        return "{" + ", ".join(values) + "}"
    # nuXmv's BDD engine is finite-state -- INT/FLOAT are approximated as a bounded integer
    # range, exact for INT but only a coarse over-approximation for FLOAT.
    lo = int(var.min_value) if var.min_value is not None else 0
    hi = int(var.max_value) if var.max_value is not None else 100
    if hi < lo:
        lo, hi = hi, lo
    return f"{lo}..{hi}"


def _build_smv_model(variables: list[Variable], formulas: list[str]) -> str:
    lines = ["MODULE main", "VAR"]
    if variables:
        for var in variables:
            lines.append(f"  {var.name} : {_smv_var_type(var)};")
    else:
        lines.append("  _unused : boolean;")  # nuXmv requires at least one declared variable
    for i, formula in enumerate(formulas):
        lines.append(f"LTLSPEC NAME p{i} := {formula}")
    return "\n".join(lines) + "\n"


def _run_nuxmv(nuxmv: Path, smv_text: str, commands: list[str]) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        model_path = Path(tmp) / "model.smv"
        model_path.write_text(smv_text)
        commands_path = Path(tmp) / "commands.txt"
        commands_path.write_text("\n".join(commands) + "\n")
        result = subprocess.run(
            [str(nuxmv), "-source", str(commands_path), str(model_path)],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL, env=_nuxmv_env(),
        )
        return result.stdout + result.stderr


_REQAN_RESULT_RE = re.compile(r"ReqAn: given requisites are( NOT)? consistent")


def check_consistency(specs: list[Specification], variables: list[Variable] | None = None) -> ConsistencyResult:
    """Checks whether a set of LTL specs can hold simultaneously, via nuXmv's ReqAn package
    (`reqan_check_consistency`) -- built for exactly this: checking a *set* of requirements
    together, rather than one formula's isolated satisfiability."""
    formulas_by_id = [(s.requirement_id, s.ltl_formula) for s in specs if s.ltl_formula]
    if not formulas_by_id:
        return ConsistencyResult(consistent=True, details="No specs to check.")

    nuxmv = _find_binary("NUXMV_PATH", "nuXmv")
    variables = variables or []
    ids = [i for i, _ in formulas_by_id]
    formulas = [f for _, f in formulas_by_id]

    def run_subset(indices: list[int]) -> bool:
        model = _build_smv_model(variables, [formulas[i] for i in indices])
        index_range = f"0-{len(indices) - 1}" if len(indices) > 1 else "0"
        output = _run_nuxmv(nuxmv, model, [
            "go", "build_boolean_model",
            f'reqan_check_consistency -i -e bdd -r "{index_range}"',
            "quit",
        ])
        match = _REQAN_RESULT_RE.search(output)
        if not match:
            raise RuntimeError(f"Couldn't parse nuXmv output:\n{output[-2000:]}")
        return match.group(1) is None

    all_indices = list(range(len(formulas)))
    if run_subset(all_indices):
        return ConsistencyResult(consistent=True, details=f"Checked {len(formulas)} requirement(s) with nuXmv.")

    # Full set is inconsistent -- isolate which requirements are involved by removing each one
    # (alone) and re-checking. Not Bendík et al.'s minimal-inconsistent-subset algorithm, but a
    # cheap, honest signal: any requirement whose removal restores consistency is part of some
    # conflicting subset.
    conflicting_ids = [
        ids[i] for i in all_indices
        if len(all_indices) > 1 and run_subset([j for j in all_indices if j != i])
    ]
    if not conflicting_ids:
        conflicting_ids = list(ids)  # couldn't isolate a smaller cause -- likely a 3+-way conflict

    return ConsistencyResult(
        consistent=False,
        conflicting_requirement_ids=conflicting_ids,
        details="Checked with nuXmv (ReqAn). Conflict isolation removes one requirement at a time "
                "and re-checks -- a good signal, but not a guaranteed-minimal subset.",
    )


_REALIZABLE_RE = re.compile(r"^(UN)?REALIZABLE", re.MULTILINE)


def check_realizability(spec: Specification, inputs: list[str], outputs: list[str]) -> RealizabilityResult:
    """GR(1)-style realizability check via Strix: does a system strategy exist that satisfies
    the spec against any adversarial input sequence from the environment?"""
    if not spec.ltl_formula:
        return RealizabilityResult(realizable=False, details="No LTL formula to check.")

    strix = _find_binary("STRIX_PATH", "strix")
    cmd = [str(strix), "-f", spec.ltl_formula, "-r"]
    if inputs:
        cmd += ["--ins", ",".join(inputs)]
    if outputs:
        cmd += ["--outs", ",".join(outputs)]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
    )
    output = (result.stdout + result.stderr).strip()
    match = _REALIZABLE_RE.search(output)
    if not match:
        if "no viable alternative" in output:
            output += (
                "\n\nThis usually means the formula uses an arithmetic/equality expression "
                "(e.g. \"classifier = 1\") as an atomic proposition -- Strix's LTL parser only "
                "accepts plain boolean propositions (bare identifiers), not comparisons over "
                "typed variables."
            )
        raise RuntimeError(f"Couldn't parse Strix output:\n{output[-2000:]}")

    realizable = match.group(1) is None
    return RealizabilityResult(realizable=realizable, details="" if realizable else output)


_STRIX_OP_WORDS = {"!=": "ne", "<=": "le", ">=": "ge", "=": "eq", "<": "lt", ">": "gt"}


def _sanitize_comparison_identifier(comparison: TypedComparison) -> str:
    """Turns a comparison like "classifier = 1" into a fresh, valid bare identifier
    ("_classifier_eq_1") Strix can accept as an atomic proposition. Checks ops longest-first so
    "!="/"<="/">=" aren't mistaken for containing "="/"<"/">"."""
    for op in sorted(_STRIX_OP_WORDS, key=len, reverse=True):
        if op in comparison.text:
            literal = comparison.text.split(op, 1)[1].strip().replace(".", "_").replace("-", "neg")
            return f"_{comparison.variable}_{_STRIX_OP_WORDS[op]}_{literal}"
    return "_" + re.sub(r"\W+", "_", comparison.text.strip())


def check_realizability_typed(formula: str, variables: list[Variable], requirement_id: str) -> RealizabilityResult:
    """Like `check_realizability`, but first abstracts any "variable OP literal" comparisons
    into fresh boolean propositions so Strix -- which only accepts bare-identifier atomic
    propositions, confirmed empirically it crashes outright on a double-quoted one (unlike
    Spot, which accepts that as a native opaque-proposition syntax) -- can check formulas built
    from typed FRET variables. Reuses the same `extract_typed_comparisons` shared helper
    `equivalence_check.py` uses for Spot/SPIN, just with fresh-name substitution standing in for
    Spot's native quoting.

    `Internal`-role variables are bucketed into the input side by default: every Internal
    variable in this project's real FRET data so far is derived purely from Input variables
    (e.g. `dgt_7 := distance_to_target > 7`), so treating it as environment-determined is
    correct for that case -- but this is a simplification, not something derived from the
    variable's actual defining expression, and would be wrong for an Internal variable that
    depends on an Output."""
    typed_names = {v.name for v in variables if v.type != VariableType.BOOL}
    comparisons, leftover = extract_typed_comparisons(formula, typed_names)
    if leftover:
        return RealizabilityResult(
            realizable=False,
            details="Strix only supports purely-boolean atomic propositions or simple \"variable "
            f"OP literal\" comparisons -- couldn't handle: {', '.join(leftover)}.",
        )

    role_by_name = {v.name: v.role for v in variables}
    renamed_formula = formula
    extra_inputs: list[str] = []
    extra_outputs: list[str] = []
    for comparison in comparisons:
        fresh_name = _sanitize_comparison_identifier(comparison)
        renamed_formula = renamed_formula.replace(comparison.text, fresh_name)
        if role_by_name.get(comparison.variable) == VariableRole.OUTPUT:
            extra_outputs.append(fresh_name)
        else:
            extra_inputs.append(fresh_name)

    # Bare Internal-role identifiers (e.g. a derived boolean like "dgt_7" referenced directly,
    # not via a comparison) also need a role bucket for Strix -- same "derived from input"
    # default as above.
    inputs = [v.name for v in variables if v.role in (VariableRole.INPUT, VariableRole.INTERNAL)] + extra_inputs
    outputs = [v.name for v in variables if v.role == VariableRole.OUTPUT] + extra_outputs

    spec = Specification(requirement_id=requirement_id, ltl_formula=renamed_formula)
    result = check_realizability(spec, inputs, outputs)

    # The fresh-name substitution is purely syntactic -- it gives Strix something it can parse,
    # but drops real relationships the original typed comparisons had (e.g. mutual exclusivity
    # between "classifier = 0"/"= 1"/"= 2", or a derived variable's correlation with the real
    # variable it comes from, like "dgt_7 -> dgt_3"), confirmed by hand-adding such a constraint
    # back into a real unrealizable case and finding it can genuinely flip the verdict. That
    # only ever hands the *environment* (input-bucketed propositions) impossible combinations it
    # wouldn't really have -- so a REALIZABLE verdict stays sound (a strategy that wins against a
    # strictly more-adversarial, over-approximated environment also wins against the real one),
    # but NOT REALIZABLE is not reliable here: it may just mean "unrealizable against an
    # abstraction artifact," not the real spec. Kind2 has no such gap, since it models these
    # variables with their real int/enum types natively.
    if comparisons and not result.realizable:
        caveat = (
            "Caveat: this formula required abstracting typed comparisons into independent fresh "
            "boolean propositions (Strix only accepts bare-identifier atomic propositions), which "
            "can drop real relationships between the original typed values -- this NOT REALIZABLE "
            "verdict may be an artifact of that missing correlation rather than a genuine "
            "synthesis failure. Kind2 models these variables natively and doesn't have this gap."
        )
        result = RealizabilityResult(realizable=False, details=(result.details + "\n\n" + caveat).strip())
    return result
