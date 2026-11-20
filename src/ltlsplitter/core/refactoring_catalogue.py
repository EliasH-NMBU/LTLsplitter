"""Requirement refactoring catalogue, adapted from Ramos et al., "Improving the Quality of
Requirements with Refactoring" (VI Simposio Brasileiro de Qualidade de Software) -- their
use-case "refactoring opportunities" (bad smells) and refactorings, translated to LTL
decomposition. Used as guidance in the LLM prompts (llm_decompose.py) so suggestions and splits
follow named, explainable patterns rather than ad-hoc judgement.

One deliberate difference from the paper: Ramos et al. note that requirements documents aren't
executable, so they "cannot fully evaluate if the behavior is preserved after the refactoring".
Here every split IS checked for equivalence and non-degeneracy by nuXmv/Spot/SPIN (stage 2),
which plays the role a test suite plays for code refactoring.
"""

from __future__ import annotations

# Values the LLM may report as the reason for (not) splitting -- see SplitSuggestion.
OPPORTUNITIES = (
    "large_requirement",
    "complex_conditional_structure",
    "duplicated_activities",
    "lazy_requirement",
    "none",
)

REFACTORING_GUIDANCE = """\
Use this refactoring catalogue (adapted from Ramos et al., "Improving the Quality of Requirements \
with Refactoring") to decide whether and how to split. A split is a behaviour-preserving \
refactoring: the conjunction of the parts must be equivalent to the original.

Refactoring opportunities ("bad smells"):
- large_requirement: one formula handles several concerns at once, e.g. a trigger whose \
response is a conjunction of independent outputs ("p -> (a & !b & c)"), or a top-level \
conjunction of unrelated obligations. Fix with Extract Requirement: one sub-formula per concern \
(typically one per output variable or per independent obligation), each keeping the full \
original trigger/guard and temporal operators.
- complex_conditional_structure: a large or nested condition, e.g. a disjunctive trigger \
"(p | q) -> r", nested implications "p -> (q -> r)", or a biconditional "p <-> q". Fix with \
Extract Alternative Flows: one sub-formula per case -- "(p -> r)" and "(q -> r)" for a \
disjunctive trigger; "(p -> q)" and "(q -> p)" for a biconditional. These splits are real even \
though no "&" appears in the formula; they follow from logical laws.
- duplicated_activities: the same sub-condition or response repeated across branches. Extract it \
so each obligation appears in exactly one sub-formula; never duplicate an obligation across parts.
- lazy_requirement: the formula is already a single obligation -- one trigger, one response, or \
a pure coupling between outputs (e.g. "!(a & b)", an "exactly one of" constraint, a parity, or \
an edge-detection pattern like "Y(p & Z !p) -> q"). Do NOT split it: any split would be \
degenerate or unsound. (The opposite refactoring, Inline Requirement, would merge such parts \
back together.)
- none: no smell present.

Rules every split must follow:
- Preserve behaviour exactly: never weaken or strengthen the original. Don't invent \
obligations, don't drop guards/triggers, keep the same temporal operators and timing \
(Y/Z/H/O/S/X/G/F/U and any bounds).
- Coupled outputs are not independent concerns: a constraint relating several outputs to each \
other must stay in one part.
- Each part must be genuinely smaller than the original and none may alone equal the whole.
- Prefer the finest split that is still made of meaningful, independently monitorable \
obligations; don't produce trivial or redundant parts.
"""
