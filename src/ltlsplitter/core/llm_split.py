from __future__ import annotations

import json
import os

import anthropic

from ltlsplitter.core.models import RequirementSplit

_MODEL = "claude-opus-5"

_SPLIT_SCHEMA = {
    "type": "object",
    "properties": {
        "sub_requirements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Each sub-requirement as a standalone, testable statement.",
        },
    },
    "required": ["sub_requirements"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You split a single natural-language software requirement into its constituent "
    "sub-requirements, each a standalone statement suitable for authoring an LTL or "
    "behavior-tree specification against. If the requirement is already atomic (it doesn't "
    "conjoin multiple obligations), return it unchanged as the sole sub-requirement. Don't "
    "invent obligations that aren't in the source text."
)


class MissingAPIKeyError(RuntimeError):
    """No Anthropic API key is configured -- neither passed explicitly nor in the environment."""


def split_requirement(requirement: str, api_key: str | None = None) -> RequirementSplit:
    """Splits a requirement into sub-requirements via the Claude Messages API. Uses
    structured outputs (output_config.format) so the response is guaranteed valid JSON
    matching the schema -- no prompt-based JSON parsing/retry loop needed."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise MissingAPIKeyError(
            "No Anthropic API key configured. Enter one above -- it's saved for next time -- "
            "or set the ANTHROPIC_API_KEY environment variable."
        )

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": requirement}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _SPLIT_SCHEMA}},
    )
    text = next(block.text for block in response.content if block.type == "text")
    data = json.loads(text)
    return RequirementSplit(original=requirement, sub_requirements=list(data["sub_requirements"]))
