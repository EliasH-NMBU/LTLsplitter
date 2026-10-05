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
