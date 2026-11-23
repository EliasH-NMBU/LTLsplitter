from __future__ import annotations

import json
import os

import anthropic

from ltlsplitter.core.models import Formalization, FretRequirement, SplitSuggestion, SubFormula, Variable
from ltlsplitter.core.refactoring_catalogue import OPPORTUNITIES, REFACTORING_GUIDANCE

_MODEL = "claude-opus-5"

_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "should_split": {
            "type": "boolean",
            "description": "Whether a split exists whose parts are together equivalent to "
            "the original, none alone equivalent to it, and whose largest part is less complex "
            "than the original.",
        },
        "rationale": {"type": "string"},
        "refactoring_opportunity": {
            "type": "string",
            "enum": list(OPPORTUNITIES),
            "description": "Which refactoring opportunity from the catalogue applies.",
        },
        "suggested_count": {
            "type": "integer",
            "description": "How many sub-formulas to split into, if should_split is true. "
            "1 if should_split is false.",
        },
    },
    "required": ["should_split", "rationale", "refactoring_opportunity", "suggested_count"],
    "additionalProperties": False,
}

_SUGGEST_SYSTEM_PROMPT = (
    "You review a single LTL requirement (given in both past-time and future-time form) and "
    "decide whether it can be split into sub-formulas that meet the criterion below: together "
    "equivalent to the original, none alone equivalent to it, and the largest part less complex "
    "than the original. Recommend a split whenever such a split exists -- including splits that "
    "follow from logical laws (disjunctive triggers, biconditionals, FRET's two trigger cases) "
    "even when no conjunction is written at the top. Don't weigh whether the split is worth "
    "it; only whether it exists. Recommend no split only when no such split exists, and then "
    "say why. Name the refactoring opportunity you identified.\n\n" + REFACTORING_GUIDANCE
)

_DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sub_formulas": {
            "type": "array",
            # No "minItems" here -- confirmed the Anthropic structured-output API rejects it
            # outright for this array ("'minItems' values other than 0 or 1 are not supported"),
            # a 400 at request time, not a soft validation warning. The "at least 2" rule for a
            # Force Split (count=None) is enforced in Python instead, after the response comes
            # back -- see decompose() below.
            "items": {
                "type": "object",
                "properties": {
                    "pt_formula": {"type": "string", "description": "Past-time LTL (H/O/S/Y)."},
                    "ft_formula": {"type": "string", "description": "Future-time LTL (G/F/X/U)."},
                },
                "required": ["pt_formula", "ft_formula"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["sub_formulas"],
    "additionalProperties": False,
}

_DECOMPOSE_SYSTEM_PROMPT = (
    "You split a single LTL requirement into sub-formulas -- exactly the requested number when "
    "one is given, or, when none is given, however many independently-checkable obligations you "
    "judge the formula naturally contains (at least 2 -- a 'split' into only one part wouldn't be "
    "one). Each sub-formula must be given in BOTH past-time form (H/O/S/Y operators, matching the "
    "style of the original past-time formula given to you) and future-time form (G/F/X/U "
    "operators, matching the style of the original future-time formula given to you) -- the two "
    "forms of each sub-formula must express the same obligation, just as the original's two "
    "forms do. The conjunction of all sub-formulas' past-time forms must be logically "
    "equivalent to the original past-time formula (and likewise for the future-time forms), and "
    "no single sub-formula may by itself already express the entire original formula's logic -- "
    "that would not be a genuine split. Don't invent obligations not present in the original.\n\n"
    + REFACTORING_GUIDANCE
)


_FORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "pt_formula": {"type": "string", "description": "Past-time LTL (H/O/S/Y/Z)."},
        "ft_formula": {"type": "string", "description": "Future-time LTL (G/F/X/U)."},
        "notes": {
            "type": "string",
            "description": "Assumptions made where the text was ambiguous, and any variable "
            "the text needs that isn't declared. Empty if none.",
        },
    },
    "required": ["pt_formula", "ft_formula", "notes"],
    "additionalProperties": False,
}

_FORMALIZE_SYSTEM_PROMPT = (
    "You translate one natural-language requirement into LTL, written the way NASA FRET "
    "writes its formulas. Give it in BOTH forms: a past-time form (H = historically, O = once, "
    "S = since, Y = yesterday, Z = weak yesterday; bounded forms like O[0,5] are allowed) that "
    "is checked at every step against the trace so far, and a future-time form (G, F, X, U) "
    "over infinite traces. Both forms must express the same obligation. Operators: & | ! -> "
    "<-> and the comparisons = != < <= > >=; constants TRUE/FALSE. Parenthesize every "
    "sub-expression fully, e.g. (H ((mode = 2) -> (! alarm))). Use only the declared variables "
    "(and the enum values listed for them); if the text needs something no variable covers, "
    "use a short descriptive identifier and say so in notes. Where the text is ambiguous, "
    "choose the most plausible reading and state it in notes. Don't add obligations the text "
    "doesn't state."
)


class MissingAPIKeyError(RuntimeError):
    """No Anthropic API key is configured -- neither passed explicitly nor in the environment."""


def _client(api_key: str | None) -> anthropic.Anthropic:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise MissingAPIKeyError(
            "No Anthropic API key configured. Enter one above -- it's saved for next time -- "
            "or set the ANTHROPIC_API_KEY environment variable."
        )
    return anthropic.Anthropic(api_key=key)


def suggest_split(pt_formula: str, ft_formula: str, api_key: str | None = None) -> SplitSuggestion:
    """Asks the LLM whether this LTL formula should be decomposed, and into how many parts."""
    client = _client(api_key)
    prompt = f"Past-time form: {pt_formula}\nFuture-time form: {ft_formula}"
    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_SUGGEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        # Not "low": deciding whether a sound, non-degenerate split exists means working the
        # formula through, and at low effort it answered from the surface pattern instead.
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _SUGGEST_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return SplitSuggestion(
        should_split=data["should_split"],
        rationale=data["rationale"],
        suggested_count=max(1, int(data["suggested_count"])),
        refactoring_opportunity=data.get("refactoring_opportunity", ""),
    )


def decompose(
    parent_id: str,
    pt_formula: str,
    ft_formula: str,
    count: int | None = None,
    api_key: str | None = None,
    feedback: str | None = None,
) -> list[SubFormula]:
    """Asks the LLM to decompose the formula into `count` sub-formulas, or, when `count` is
    None, into however many sub-formulas the LLM itself judges appropriate (at least 2).
    `feedback`, when given, carries a prior validation failure's details back to the LLM to
    correct on retry."""
    client = _client(api_key)
    if count is None:
        prompt = (
            f"Past-time form: {pt_formula}\nFuture-time form: {ft_formula}\n"
            "Split this into multiple independently-checkable sub-formulas. Decide how many "
            "sub-formulas are appropriate yourself -- there is no fixed target count."
        )
    else:
        prompt = (
            f"Past-time form: {pt_formula}\nFuture-time form: {ft_formula}\n"
            f"Split into exactly {count} sub-formula(s)."
        )
    if feedback:
        prompt += f"\n\nA previous attempt failed validation: {feedback}\nTry again, fixing this."

    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_DECOMPOSE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _DECOMPOSE_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    if count is None and len(data["sub_formulas"]) < 2:
        # The schema can't enforce "at least 2" itself (Anthropic's structured-output API
        # rejects any minItems other than 0/1), so this is caught here instead of shipping a
        # single-part "split" that wouldn't actually be one.
        raise RuntimeError(
            "The LLM couldn't find a genuine split for this formula -- it returned only one "
            "part even though Force Split asked for multiple."
        )
    return [
        SubFormula(id=f"{parent_id}.{i + 1}", pt_formula=item["pt_formula"], ft_formula=item["ft_formula"])
        for i, item in enumerate(data["sub_formulas"])
    ]


def _describe_variable(var: Variable) -> str:
    text = f"{var.name}: {var.type.value}, {var.role.value}"
    if var.enum_values:
        text += f", values {{{', '.join(var.enum_values)}}}"
    if var.min_value is not None or var.max_value is not None:
        text += f", range {var.min_value if var.min_value is not None else '?'}..{var.max_value if var.max_value is not None else '?'}"
    if var.assignment:
        text += f", defined as {var.assignment}"
    return text


def formalize(
    natural_language: str,
    variables: list[Variable],
    examples: list[FretRequirement] = (),
    api_key: str | None = None,
) -> Formalization:
    """Asks the LLM to turn a natural-language requirement into past- and future-time LTL over
    the declared `variables`. `examples` (a few requirements from the same file) show it the
    project's own formula style."""
    client = _client(api_key)
    prompt = "Declared variables:\n" + ("\n".join(f"- {_describe_variable(v)}" for v in variables) or "(none)")
    if examples:
        prompt += "\n\nExamples from the same project:\n" + "\n".join(
            f"- \"{ex.fulltext}\"\n  pt: {ex.pt_formula}\n  ft: {ex.ft_formula}" for ex in examples
        )
    prompt += f"\n\nRequirement to translate:\n{natural_language}"
    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_FORMALIZE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": _FORMALIZE_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return Formalization(pt_formula=data["pt_formula"], ft_formula=data["ft_formula"], notes=data.get("notes", ""))
