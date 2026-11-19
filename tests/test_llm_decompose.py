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
