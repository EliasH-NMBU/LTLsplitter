from ltlsplitter.core.project_state import ProjectState


def test_requirement_ids_fallback_to_original():
    state = ProjectState(original_requirement="the system shall do X")
    assert state.requirement_ids() == ["R1"]
    assert state.requirement_text("R1") == "the system shall do X"


def test_requirement_ids_from_sub_requirements():
    state = ProjectState(sub_requirements=["a", "b"])
    assert state.requirement_ids() == ["r1.1", "r1.2"]
    assert state.requirement_text("r1.2") == "b"


def test_no_requirement_ids_when_nothing_entered():
    assert ProjectState().requirement_ids() == []


def test_spec_for_creates_once_and_reuses():
    state = ProjectState()
    spec = state.spec_for("R1")
    spec.ltl_formula = "G a"

    assert state.spec_for("R1") is spec
    assert state.spec_for("R1").ltl_formula == "G a"
