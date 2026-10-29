from ltlsplitter.core.models import FretImport, FretRequirement, SubFormula
from ltlsplitter.core.project_state import ProjectState


def _fret_import() -> FretImport:
    return FretImport(
        project="demo",
        requirements=[
            FretRequirement(reqid="r1", fulltext="...", pt_formula="(H (a -> b))", ft_formula="(G (a -> b))"),
        ],
    )


def test_active_sub_formulas_empty_when_nothing_selected():
    assert ProjectState().active_sub_formulas() == []


def test_active_sub_formulas_falls_back_to_original_when_not_split():
    state = ProjectState(fret_import=_fret_import(), selected_requirement_id="r1")

    formulas = state.active_sub_formulas()

    assert len(formulas) == 1
    assert formulas[0] == SubFormula(id="r1", pt_formula="(H (a -> b))", ft_formula="(G (a -> b))")


def test_active_sub_formulas_uses_accepted_split():
    sub_formulas = [
        SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)"),
        SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)"),
    ]
    state = ProjectState(
        fret_import=_fret_import(),
        selected_requirement_id="r1",
        split_accepted=True,
        sub_formulas=sub_formulas,
    )

    assert state.active_sub_formulas() == sub_formulas


def test_active_sub_formulas_ignores_stale_split_when_not_accepted():
    state = ProjectState(
        fret_import=_fret_import(),
        selected_requirement_id="r1",
        split_accepted=False,
        sub_formulas=[SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)")],
    )

    formulas = state.active_sub_formulas()

    assert len(formulas) == 1
    assert formulas[0].id == "r1"


def test_active_sub_formulas_finds_an_already_saved_split_by_parent_reqid():
    # Regression test: selecting a requirement that was split and saved in an earlier session
    # (or just re-selected after the in-memory split state was reset -- e.g. by
    # `_save_split`'s own tree refresh, see import_split.py's `_on_requirement_selected`)
    # must still find its real sub-formulas instead of falling back to "not split", which
    # made stage 2 wrongly report "nothing to validate" for a split that was, in fact, saved.
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(reqid="r1", fulltext="...", pt_formula="(H (a -> b))", ft_formula="(G (a -> b))"),
            FretRequirement(reqid="r1.1", fulltext="...", pt_formula="(H a)", ft_formula="(G a)", parent_reqid="r1"),
            FretRequirement(reqid="r1.2", fulltext="...", pt_formula="(H b)", ft_formula="(G b)", parent_reqid="r1"),
        ],
    )
    state = ProjectState(fret_import=fret_import, selected_requirement_id="r1")

    formulas = state.active_sub_formulas()

    assert [f.id for f in formulas] == ["r1.1", "r1.2"]
    assert formulas[0] == SubFormula(id="r1.1", pt_formula="(H a)", ft_formula="(G a)")
    assert formulas[1] == SubFormula(id="r1.2", pt_formula="(H b)", ft_formula="(G b)")


def test_active_sub_formulas_prefers_in_session_split_over_a_saved_one():
    fret_import = FretImport(
        project="demo",
        requirements=[
            FretRequirement(reqid="r1", fulltext="...", pt_formula="(H (a -> b))", ft_formula="(G (a -> b))"),
            FretRequirement(reqid="r1.1", fulltext="...", pt_formula="(H a)", ft_formula="(G a)", parent_reqid="r1"),
        ],
    )
    fresh_split = [SubFormula(id="r1.new", pt_formula="(H c)", ft_formula="(G c)")]
    state = ProjectState(
        fret_import=fret_import,
        selected_requirement_id="r1",
        split_accepted=True,
        sub_formulas=fresh_split,
    )

    assert state.active_sub_formulas() == fresh_split
