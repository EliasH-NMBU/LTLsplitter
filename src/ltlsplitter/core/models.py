from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VariableType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ENUM = "enum"


class VariableRole(str, Enum):
    """Environment (input) vs. system-controlled (output) vs. derived (internal) -- mirrors
    FRET's idType. Realizability only cares about input/output; internal variables are
    substituted via their `assignment` expression instead."""

    INPUT = "input"
    OUTPUT = "output"
    INTERNAL = "internal"


@dataclass
class Variable:
    name: str
    type: VariableType
    ros_node: str = ""
    role: VariableRole = VariableRole.INPUT
    min_value: float | None = None
    max_value: float | None = None
    enum_values: list[str] = field(default_factory=list)
    assignment: str | None = None
    """For role=INTERNAL: the defining expression in SMV/Lustre-ish syntax (FRET's
    `assignment`), e.g. "distance_to_target > 3" -- used by the nuXmv/Spot/SPIN equivalence
    checks, which need a plain boolean/arithmetic expression."""
    copilot_assignment: str | None = None
    """Same, but in Copilot syntax (FRET's `copilotAssignment`), e.g.
    "distance_to_target > constant 3" -- used for Ogma export, which embeds it directly into
    generated Copilot/Haskell code."""


@dataclass
class Specification:
    requirement_id: str
    ltl_formula: str | None = None
    behavior_tree_xml: str | None = None
    variables: list[Variable] = field(default_factory=list)


@dataclass
class ConsistencyResult:
    consistent: bool
    conflicting_requirement_ids: list[str] = field(default_factory=list)
    details: str = ""


@dataclass
class RealizabilityResult:
    realizable: bool
    counterexample: str | None = None
    details: str = ""


@dataclass
class FretRequirement:
    """One requirement as imported from a FRET project export."""

    reqid: str
    fulltext: str
    pt_formula: str
    ft_formula: str
    variable_names: list[str] = field(default_factory=list)
    parent_reqid: str = ""
    """FRET's own convention for marking a requirement as a sub-part of another (seen in real
    FRET realizability exports) -- also what this project writes when a split's sub-formulas
    are saved back out, so the GUI can show them nested under the original they came from."""
    is_assumption: bool = False
    """Whether this is an environment assumption (a constraint the system benefits from but
    doesn't have to enforce itself) rather than a system guarantee. FRET's export has no
    structural field for this -- only a naming convention (e.g. "classifier_assumption") seen in
    real data -- so this is seeded as a heuristic default on import and left for the user to
    correct, never trusted silently. Guaranteeing an assumption as if it were a guarantee makes
    realizability checks fail on formulas the system never controlled in the first place (e.g.
    "classifier is in {0,1,2}" when classifier is an input)."""


@dataclass
class FretImport:
    """A whole FRET project export: every requirement and every variable it declares."""

    project: str
    requirements: list[FretRequirement] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)

    def requirement(self, reqid: str) -> FretRequirement | None:
        return next((r for r in self.requirements if r.reqid == reqid), None)

    def leaf_requirements(self) -> list[FretRequirement]:
        """Every requirement that isn't itself the parent of others -- i.e. the "current" form
        of each original obligation: a split's sub-formulas once saved (see
        `fret_import.append_sub_formulas_and_save`), or the requirement's own formula if it was
        never split. A requirement that *has* children is excluded here since its own formula
        is logically superseded by them (stage 2 already proved they're equivalent to it), so
        including both would just be redundant, not wrong -- this is what "the entire system"
        means for a realizability check: every current obligation counted exactly once."""
        parent_ids = {r.parent_reqid for r in self.requirements if r.parent_reqid}
        return [r for r in self.requirements if r.reqid not in parent_ids]


@dataclass
class SplitSuggestion:
    should_split: bool
    rationale: str
    suggested_count: int = 1


@dataclass
class SubFormula:
    id: str
    pt_formula: str
    ft_formula: str


@dataclass
class ToolCheckResult:
    tool: str
    passed: bool
    details: str = ""


@dataclass
class DecompositionValidation:
    """Result of cross-checking a decomposition against its original formula with all
    available model checkers: one equivalence result per tool, plus one non-degeneracy
    result per tool per sub-formula."""

    equivalence: list[ToolCheckResult] = field(default_factory=list)
    nondegeneracy: dict[str, list[ToolCheckResult]] = field(default_factory=dict)

    @property
    def all_passed(self) -> bool:
        if not self.equivalence:
            return False
        if not all(r.passed for r in self.equivalence):
            return False
        return all(r.passed for results in self.nondegeneracy.values() for r in results)
