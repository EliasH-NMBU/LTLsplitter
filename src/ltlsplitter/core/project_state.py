from __future__ import annotations

from dataclasses import dataclass, field

from ltlsplitter.core.models import (
    DecompositionValidation,
    FretImport,
    RealizabilityResult,
    SplitSuggestion,
    SubFormula,
)


@dataclass
class ProjectState:
    """In-memory state shared across wizard pages for a single FRET requirement being split,
    validated, and exported."""

    fret_import: FretImport | None = None
    selected_requirement_id: str | None = None
    split_suggestion: SplitSuggestion | None = None
    split_accepted: bool = False
    sub_formulas: list[SubFormula] = field(default_factory=list)
    validation: DecompositionValidation | None = None
    realizability_result: RealizabilityResult | None = None
    generated_monitor_path: str = ""

    def active_sub_formulas(self) -> list[SubFormula]:
        """What pages 2-4 operate on: the accepted decomposition if there is one, otherwise
        a single sub-formula standing in for the unmodified original requirement."""
        if self.split_accepted and self.sub_formulas:
            return self.sub_formulas
        if self.fret_import is None or self.selected_requirement_id is None:
            return []
        req = self.fret_import.requirement(self.selected_requirement_id)
        if req is None:
            return []
        return [SubFormula(id=req.reqid, pt_formula=req.pt_formula, ft_formula=req.ft_formula)]
