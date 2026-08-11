from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ltlsplitter.core.models import Specification, Variable, VariableType

_LOCAL_BIN = Path.home() / ".local" / "bin"
_SUBPROCESS_TIMEOUT_SECONDS = 60

# Static JSONPath-style format description telling ogma how to read the expressions.json
# this module generates -- see ogma-cli's ros2-001-hello-ogma example, which this mirrors.
_FORMAT_CFG = """JSONFormat
   { specInternalVars          = Just "..internal_variables[*]"
   , specInternalVarId         = ".name"
   , specInternalVarExpr       = ".meaning"
   , specInternalVarType       = Just ".type"
   , specExternalVars          = Just "..external_variables[*]"
   , specExternalVarId         = ".name"
   , specExternalVarType       = Just ".type"
   , specRequirements          = "..properties[*]"
   , specRequirementId         = ".id"
   , specRequirementDesc       = Just ".text"
   , specRequirementExpr       = ".formula"
   , specRequirementResultType = Nothing
   , specRequirementResultExpr = Nothing
   }
"""

# Two distinct type vocabularies feed into ogma: variable-db.json wants the C type
# (embedded in the generated C++ subscriber), while expressions.json wants the
# Copilot/Haskell stream type name (embedded in the generated Haskell spec) -- e.g.
# C "int32_t" vs Haskell "Int32". Confirmed against ogma-cli's own ROS2 tutorial example.
_C_TYPES = {
    VariableType.BOOL: "bool",
    VariableType.INT: "int32_t",
    VariableType.FLOAT: "double",
    VariableType.ENUM: "int32_t",  # Copilot has no string stream type -- enums become an index
}

_COPILOT_TYPES = {
    VariableType.BOOL: "Bool",
    VariableType.INT: "Int32",
    VariableType.FLOAT: "Double",
    VariableType.ENUM: "Int32",
}

_ROS_MSG_TYPES = {
    VariableType.BOOL: "std_msgs::msg::Bool",
    VariableType.INT: "std_msgs::msg::Int32",
    VariableType.FLOAT: "std_msgs::msg::Float64",
    VariableType.ENUM: "std_msgs::msg::Int32",
}


class ToolNotFoundError(RuntimeError):
    """Ogma isn't installed or can't be located."""


def _find_ogma() -> Path:
    override = os.environ.get("OGMA_PATH")
    if override:
        path = Path(override)
        if path.is_file():
            return path
        raise ToolNotFoundError(f"OGMA_PATH is set to '{override}' but that file doesn't exist.")
    which = shutil.which("ogma")
    if which:
        return Path(which)
    candidate = _LOCAL_BIN / "ogma"
    if candidate.is_file():
        return candidate
    raise ToolNotFoundError(
        "Couldn't find 'ogma'. Install it (see README.md -- requires GHC/Cabal/Z3), then either "
        "add it to your PATH, symlink it into ~/.local/bin, or set OGMA_PATH to its full path."
    )


def patch_cmake_for_modern_ament(package_dir: Path) -> None:
    """Ogma's generated CMakeLists.txt calls ament_target_dependencies(), which this
    ROS2 release (Lyrical) has fully removed in favor of target_link_libraries() with
    imported targets -- confirmed by hand while building this integration: colcon build
    otherwise fails with 'Unknown CMake command "ament_target_dependencies"'."""
    cmake_path = package_dir / "copilot" / "CMakeLists.txt"
    if not cmake_path.is_file():
        return
    text = cmake_path.read_text()
    old = "ament_target_dependencies(copilot\n  rclcpp\n  std_msgs\n)"
    new = "target_link_libraries(copilot\n  rclcpp::rclcpp\n  ${std_msgs_TARGETS}\n)"
    if old in text:
        cmake_path.write_text(text.replace(old, new))


def _sanitize_id(requirement_id: str) -> str:
    """Ogma turns the requirement id into a Haskell/C identifier (e.g. a `handler<Id>`
    function name) -- our ids like "r1.1" contain characters that aren't valid there."""
    return "".join(c if c.isalnum() else "_" for c in requirement_id)


def _build_expressions_json(spec: Specification, variables: list[Variable]) -> dict:
    return {
        "Spec": {
            "internal_variables": [],
            "external_variables": [{"name": v.name, "type": _COPILOT_TYPES[v.type]} for v in variables],
            "properties": [
                {"id": _sanitize_id(spec.requirement_id), "formula": spec.ltl_formula, "text": ""}
            ],
        }
    }


def _build_variable_db(variables: list[Variable]) -> dict:
    inputs, topics = [], []
    for var in variables:
        topic = f"/{var.name}"
        inputs.append({
            "name": var.name,
            "type": _C_TYPES[var.type],
            "active": True,
            "connections": [{"scope": "ros/message", "topic": topic}],
        })
        topics.append({"scope": "ros/message", "topic": topic, "type": _ROS_MSG_TYPES[var.type]})
    return {"inputs": inputs, "topics": topics, "types": []}


def generate_ros2_monitor(
    spec: Specification, output_dir: Path, variables: list[Variable] | None = None
) -> Path:
    """Shells out to `ogma ros` to generate a ROS2 monitor package from a spec.

    Ogma's LTL parser (ogma-cli 1.15.0) accepts a single temporal operator wrapping an
    otherwise-propositional formula (e.g. "G (x)", "H (x -> y)") but not formulas with
    *nested* temporal operators (e.g. "G (x -> F y)", one of the most common LTL
    patterns) -- confirmed empirically against the installed tool, not a limitation of
    this wiring. Such formulas fail with a misleadingly worded "cannot open input
    specification file" error from ogma itself; that case is detected and clarified
    below rather than left cryptic."""
    if not spec.ltl_formula:
        raise ValueError("This spec has no LTL formula to generate a monitor from.")

    ogma = _find_ogma()
    variables = variables or []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        expressions_path = tmp_path / "expressions.json"
        format_path = tmp_path / "format.cfg"
        variable_db_path = tmp_path / "variable-db.json"

        expressions_path.write_text(json.dumps(_build_expressions_json(spec, variables), indent=2))
        format_path.write_text(_FORMAT_CFG)
        variable_db_path.write_text(json.dumps(_build_variable_db(variables), indent=2))

        result = subprocess.run(
            [
                str(ogma), "ros",
                "--target-dir", str(output_dir),
                "--input-file", str(expressions_path),
                "--input-format", str(format_path),
                "--prop-format", "smv",
                "--variable-db", str(variable_db_path),
            ],
            capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )

    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        if "cannot open input specification file" in output:
            output += (
                "\n\nThis usually means the formula nests one temporal operator inside another "
                "(e.g. \"G (x -> F y)\") -- ogma's parser only supports a single temporal "
                "operator wrapping an otherwise-propositional formula."
            )
        raise RuntimeError(f"ogma failed:\n{output}")

    patch_cmake_for_modern_ament(output_dir)
    return output_dir
