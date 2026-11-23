import json

import pytest

from ltlsplitter.core.llm_decompose import _DECOMPOSE_SCHEMA, decompose


class _FakeBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _FakeResponse:
    def __init__(self, data: dict):
        self.content = [_FakeBlock(json.dumps(data))]


class _FakeMessages:
    def __init__(self, data: dict):
        self._data = data
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._data)


class _FakeClient:
    def __init__(self, data: dict):
        self.messages = _FakeMessages(data)


def _patch_client(monkeypatch, data: dict) -> _FakeClient:
    client = _FakeClient(data)
    monkeypatch.setattr("ltlsplitter.core.llm_decompose._client", lambda api_key: client)
    return client


def test_decompose_schema_never_uses_min_items():
    """Regression guard for a real bug: the Anthropic structured-output API rejects any
    "minItems" other than 0 or 1 with a 400 ("'minItems' values other than 0 or 1 are not
    supported") -- this must never creep back in, even on just one property."""
    assert "minItems" not in json.dumps(_DECOMPOSE_SCHEMA)


def test_force_split_raises_when_the_llm_returns_only_one_part(monkeypatch):
    """count=None is the Force Split path -- a single-item result isn't a genuine split, and
    since the schema can no longer enforce "at least 2" itself (see the test above), this has
    to be caught in Python after the response comes back."""
    _patch_client(monkeypatch, {"sub_formulas": [{"pt_formula": "(H a)", "ft_formula": "(G a)"}]})

    with pytest.raises(RuntimeError, match="only one part"):
        decompose("r1", "(H a)", "(G a)", count=None, api_key="sk-test")


def test_force_split_succeeds_with_two_or_more_parts(monkeypatch):
    _patch_client(monkeypatch, {
        "sub_formulas": [
            {"pt_formula": "(H a)", "ft_formula": "(G a)"},
            {"pt_formula": "(H b)", "ft_formula": "(G b)"},
        ],
    })

    result = decompose("r1", "(H (a & b))", "(G (a & b))", count=None, api_key="sk-test")

    assert [s.id for s in result] == ["r1.1", "r1.2"]
    assert result[0].pt_formula == "(H a)"
    assert result[1].pt_formula == "(H b)"


def test_exact_count_request_does_not_apply_the_at_least_two_guard(monkeypatch):
    """An exact count (the normal Accept-suggestion path, not Force Split) is allowed to come
    back with just one part -- e.g. suggest_split's own suggested_count can legitimately be 1."""
    client = _patch_client(monkeypatch, {"sub_formulas": [{"pt_formula": "(H a)", "ft_formula": "(G a)"}]})

    result = decompose("r1", "(H a)", "(G a)", count=1, api_key="sk-test")

    assert len(result) == 1
    assert "exactly 1 sub-formula(s)" in client.messages.calls[0]["messages"][0]["content"]


def test_force_split_prompt_states_there_is_no_fixed_target_count(monkeypatch):
    client = _patch_client(monkeypatch, {
        "sub_formulas": [
            {"pt_formula": "(H a)", "ft_formula": "(G a)"},
            {"pt_formula": "(H b)", "ft_formula": "(G b)"},
        ],
    })

    decompose("r1", "(H a)", "(G a)", count=None, api_key="sk-test")

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "no fixed target count" in prompt


def test_suggest_split_reports_the_refactoring_opportunity(monkeypatch):
    from ltlsplitter.core.llm_decompose import suggest_split

    client = _patch_client(monkeypatch, {
        "should_split": True, "rationale": "two outputs",
        "refactoring_opportunity": "large_requirement", "suggested_count": 2,
    })

    result = suggest_split("(H (p -> (a & b)))", "(G (p -> (a & b)))", api_key="sk-test")

    assert result.refactoring_opportunity == "large_requirement"
    assert "Extract Requirement" in client.messages.calls[0]["system"]


def test_decompose_prompt_includes_the_refactoring_catalogue(monkeypatch):
    client = _patch_client(monkeypatch, {
        "sub_formulas": [
            {"pt_formula": "(H a)", "ft_formula": "(G a)"},
            {"pt_formula": "(H b)", "ft_formula": "(G b)"},
        ],
    })

    decompose("r1", "(H (a & b))", "(G (a & b))", count=None, api_key="sk-test")

    system = client.messages.calls[0]["system"]
    assert "lazy_requirement" in system and "Extract Alternative Flows" in system


def test_suggest_schema_has_no_unsupported_min_items():
    from ltlsplitter.core.llm_decompose import _SUGGEST_SCHEMA
    assert "minItems" not in json.dumps(_SUGGEST_SCHEMA)


def test_formalize_sends_declared_variables_and_style_examples(monkeypatch):
    from ltlsplitter.core.llm_decompose import formalize
    from ltlsplitter.core.models import FretRequirement, Variable, VariableType

    client = _patch_client(monkeypatch, {
        "pt_formula": "(H ((mode = run) -> alarm))", "ft_formula": "(G ((mode = run) -> alarm))", "notes": "",
    })
    variables = [
        Variable(name="mode", type=VariableType.ENUM, enum_values=["idle", "run"]),
        Variable(name="alarm", type=VariableType.BOOL),
    ]
    example = FretRequirement(reqid="r0", fulltext="Always idle.", pt_formula="(H (mode = idle))", ft_formula="(G (mode = idle))")

    result = formalize("When running, the alarm shall be on.", variables, [example], api_key="sk-test")

    assert result.pt_formula == "(H ((mode = run) -> alarm))"
    assert result.ft_formula == "(G ((mode = run) -> alarm))"
    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "mode: enum, input, values {idle, run}" in prompt
    assert "(H (mode = idle))" in prompt
    assert "When running, the alarm shall be on." in prompt


def test_formalize_schema_has_no_unsupported_min_items():
    from ltlsplitter.core.llm_decompose import _FORMALIZE_SCHEMA
    assert "minItems" not in json.dumps(_FORMALIZE_SCHEMA)
