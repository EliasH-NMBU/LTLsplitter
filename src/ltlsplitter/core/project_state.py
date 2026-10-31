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
    fret_import_path: str = ""
    """Where fret_import was most recently loaded from -- the base a split's sub-formulas get
    appended to (as a new copy, never overwriting this file) when the user saves a split."""
    selected_requirement_id: str | None = None
    split_suggestion: SplitSuggestion | None = None
    split_accepted: bool = False
    sub_formulas: list[SubFormula] = field(default_factory=list)
    validation: DecompositionValidation | None = None
    realizability_results: dict[str, RealizabilityResult] = field(default_factory=dict)
    """Keyed by tool name ("Strix", "Kind2") -- each checks realizability independently via a
    different algorithm (game synthesis vs. SMT/k-induction contract analysis), run side by
    side as a cross-check rather than one replacing the other."""
    generated_monitor_path: str = ""

    def active_sub_formulas(self) -> list[SubFormula]:
        """What pages 2-4 operate on, in priority order: (1) a split just accepted in this
        session, (2) an already-saved split's children -- looked up by `parent_reqid`, so
        re-selecting a previously-split requirement (even after reloading the import, or
        without ever re-running the split in this session) still finds its real sub-formulas
        instead of looking "not split" -- or (3), if neither applies, a single sub-formula
        standing in for the unmodified original requirement."""
        if self.split_accepted and self.sub_formulas:
            return self.sub_formulas
        if self.fret_import is None or self.selected_requirement_id is None:
            return []
        req = self.fret_import.requirement(self.selected_requirement_id)
        if req is None:
            return []
        children = [r for r in self.fret_import.requirements if r.parent_reqid == req.reqid]
        if children:
            return [SubFormula(id=c.reqid, pt_formula=c.pt_formula, ft_formula=c.ft_formula) for c in children]
        return [SubFormula(id=req.reqid, pt_formula=req.pt_formula, ft_formula=req.ft_formula)]
