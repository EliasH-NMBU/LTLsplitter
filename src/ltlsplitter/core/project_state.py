from __future__ import annotations

from dataclasses import dataclass, field

from ltlsplitter.core.models import Specification, Variable


@dataclass
class ProjectState:
    """In-memory state shared across wizard pages for a single requirement being worked on."""

    original_requirement: str = ""
    sub_requirements: list[str] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    specifications: dict[str, Specification] = field(default_factory=dict)
    generated_monitor_path: str = ""

    def requirement_ids(self) -> list[str]:
        if self.sub_requirements:
            return [f"r1.{i + 1}" for i in range(len(self.sub_requirements))]
        if self.original_requirement:
            return ["R1"]
        return []

    def requirement_text(self, requirement_id: str) -> str:
        if self.sub_requirements:
            index = self.requirement_ids().index(requirement_id)
            return self.sub_requirements[index]
        return self.original_requirement

    def spec_for(self, requirement_id: str) -> Specification:
        return self.specifications.setdefault(requirement_id, Specification(requirement_id=requirement_id))
