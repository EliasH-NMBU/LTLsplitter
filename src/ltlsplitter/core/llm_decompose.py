from __future__ import annotations

import json
import os

import anthropic

from ltlsplitter.core.models import SplitSuggestion, SubFormula

_MODEL = "claude-opus-5"

_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "should_split": {
            "type": "boolean",
            "description": "Whether this LTL formula conjoins multiple independently-"
            "monitorable obligations and would benefit from being split into sub-properties.",
        },
        "rationale": {"type": "string"},
        "suggested_count": {
            "type": "integer",
            "description": "How many sub-formulas to split into, if should_split is true. "
            "1 if should_split is false.",
        },
    },
    "required": ["should_split", "rationale", "suggested_count"],
    "additionalProperties": False,
}

_SUGGEST_SYSTEM_PROMPT = (
    "You review a single LTL requirement (given in both past-time and future-time form) and "
    "judge whether it conjoins multiple independently-checkable obligations that would be "
    "clearer and easier to runtime-monitor as separate sub-properties, versus being already "
    "atomic. Be conservative: only recommend a split when the formula's top-level structure "
    "genuinely separates (e.g. a conjunction of unrelated consequents), not just because it's "
    "long or deeply nested."
)

_DECOMPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "sub_formulas": {
            "type": "array",
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
    "You split a single LTL requirement into exactly the requested number of sub-formulas. "
    "Each sub-formula must be given in BOTH past-time form (H/O/S/Y operators, matching the "
    "style of the original past-time formula given to you) and future-time form (G/F/X/U "
    "operators, matching the style of the original future-time formula given to you) -- the two "
    "forms of each sub-formula must express the same obligation, just as the original's two "
    "forms do. The conjunction of all sub-formulas' past-time forms must be logically "
    "equivalent to the original past-time formula (and likewise for the future-time forms), and "
    "no single sub-formula may by itself already express the entire original formula's logic -- "
    "that would not be a genuine split. Don't invent obligations not present in the original."
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
        max_tokens=1024,
        system=_SUGGEST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SUGGEST_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return SplitSuggestion(
        should_split=data["should_split"],
        rationale=data["rationale"],
        suggested_count=max(1, int(data["suggested_count"])),
    )


def decompose(
    parent_id: str,
    pt_formula: str,
    ft_formula: str,
    count: int,
    api_key: str | None = None,
    feedback: str | None = None,
) -> list[SubFormula]:
    """Asks the LLM to decompose the formula into `count` sub-formulas. `feedback`, when given,
    carries a prior validation failure's details back to the LLM to correct on retry."""
    client = _client(api_key)
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
    return [
        SubFormula(id=f"{parent_id}.{i + 1}", pt_formula=item["pt_formula"], ft_formula=item["ft_formula"])
        for i, item in enumerate(data["sub_formulas"])
    ]
