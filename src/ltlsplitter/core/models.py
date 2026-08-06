from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VariableType(str, Enum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    ENUM = "enum"


@dataclass
class Variable:
    name: str
    type: VariableType
    ros_node: str
    min_value: float | None = None
    max_value: float | None = None
    enum_values: list[str] = field(default_factory=list)


@dataclass
class RequirementSplit:
    original: str
    sub_requirements: list[str] = field(default_factory=list)


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
