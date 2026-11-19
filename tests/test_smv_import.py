from pathlib import Path

import pytest

from .conftest import requires_nuxmv, requires_spin, requires_spot

from ltlsplitter.core.equivalence_check import _check_tautology_nuxmv, _check_tautology_spin, _check_tautology_spot
from ltlsplitter.core.models import VariableType
from ltlsplitter.core.smv_import import InvalidSmvFileError, import_smv_file

_FIXTURES = Path(__file__).parent / "fixtures" / "smvUseCases"


def _write(tmp_path, text: str, name: str = "model.smv") -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_missing_file_raises_invalid_smv_error(tmp_path):
    with pytest.raises(InvalidSmvFileError):
        import_smv_file(tmp_path / "does_not_exist.smv")


def test_file_with_no_ltlspec_raises_invalid_smv_error(tmp_path):
    path = _write(tmp_path, "MODULE main\nVAR x : boolean;\n")
    with pytest.raises(InvalidSmvFileError):
        import_smv_file(path)


def test_parses_a_single_future_time_ltlspec(tmp_path):
    path = _write(tmp_path, "VAR a : boolean;\nVAR b : boolean;\nLTLSPEC G (a -> X b);\n")
    fi = import_smv_file(path)

    assert len(fi.requirements) == 1
    req = fi.requirements[0]
    assert req.ft_formula == "G (a -> X b)"
    assert req.pt_formula == ""
    assert set(req.variable_names) == {"a", "b"}


def test_parses_a_past_time_ltlspec_into_pt_formula_only(tmp_path):
    path = _write(tmp_path, "VAR a : boolean;\nLTLSPEC H (Y a);\n")
    fi = import_smv_file(path)

    req = fi.requirements[0]
    assert req.pt_formula == "H (Y a)"
    assert req.ft_formula == ""


def test_mixed_past_and_future_operators_go_entirely_to_pt_formula(tmp_path):
    """Spot/SPIN can't parse even one past-time operator, confirmed elsewhere in this codebase
    -- a formula using both kinds is only ever checkable via nuXmv, so it belongs in pt_formula
    alone, not split or duplicated into ft_formula too."""
    path = _write(tmp_path, "VAR a : boolean;\nVAR b : boolean;\nLTLSPEC G (a -> (Y b));\n")
    fi = import_smv_file(path)

    req = fi.requirements[0]
    assert req.pt_formula == "G (a -> (Y b))"
    assert req.ft_formula == ""


def test_named_ltlspec_uses_the_given_name_as_reqid(tmp_path):
    path = _write(tmp_path, "VAR a : boolean;\nLTLSPEC NAME my_prop := G a;\n")
    fi = import_smv_file(path)

    assert fi.requirements[0].reqid == "my_prop"


def test_unnamed_ltlspecs_get_sequential_generated_reqids(tmp_path):
    path = _write(tmp_path, "VAR a : boolean;\nLTLSPEC G a;\nLTLSPEC G (! a);\n")
    fi = import_smv_file(path)

    assert [r.reqid for r in fi.requirements] == ["smv_req_1", "smv_req_2"]


def test_last_ltlspec_without_a_trailing_semicolon_still_parses(tmp_path):
    """Confirmed against the real nuXmv binary (see krca1p1.smv in smvUseCases/) that this is
    valid input, not malformed -- the parser doesn't require a ";" on the file's last statement."""
    path = _write(tmp_path, "VAR a : boolean;\nLTLSPEC G a")
    fi = import_smv_file(path)

    assert fi.requirements[0].ft_formula == "G a"


def test_comments_are_stripped_before_parsing(tmp_path):
    path = _write(tmp_path, "-- a comment with LTLSPEC in it should not confuse anything\nVAR a : boolean;\nLTLSPEC G a; -- trailing comment\n")
    fi = import_smv_file(path)

    assert len(fi.requirements) == 1
    assert fi.requirements[0].ft_formula == "G a"


def test_variable_types_are_parsed_boolean_range_enum_and_real(tmp_path):
    path = _write(
        tmp_path,
        "VAR flag : boolean;\nVAR mode : 0..3;\nVAR state : {idle, running, done};\nVAR temp : real;\nLTLSPEC G flag;\n",
    )
    fi = import_smv_file(path)
    by_name = {v.name: v for v in fi.variables}

    assert by_name["flag"].type == VariableType.BOOL
    assert by_name["mode"].type == VariableType.INT
    assert (by_name["mode"].min_value, by_name["mode"].max_value) == (0.0, 3.0)
    assert by_name["state"].type == VariableType.ENUM
    assert by_name["state"].enum_values == ["idle", "running", "done"]
    assert by_name["temp"].type == VariableType.FLOAT


def test_enum_literal_referenced_in_a_formula_is_not_mistaken_for_a_second_variable(tmp_path):
    """The exact bug found against growing-counter-integer.smv: "state = s3" references the
    literal s3, not a variable named s3."""
    path = _write(tmp_path, "VAR state : {s0, s1, s2, s3};\nLTLSPEC G F (state = s3);\n")
    fi = import_smv_file(path)

    assert {v.name for v in fi.variables} == {"state"}
    assert fi.requirements[0].variable_names == ["state"]


def test_undeclared_identifiers_are_auto_added_as_boolean_variables(tmp_path):
    """A bare list of formulas with no VAR section at all -- every referenced identifier is
    still a real variable, just an undeclared one, defaulted to boolean rather than dropped."""
    path = _write(tmp_path, "LTLSPEC G (a -> F b);\n")
    fi = import_smv_file(path)

    assert {v.name for v in fi.variables} == {"a", "b"}
    assert fi.variables[0].type == VariableType.BOOL


def test_project_name_comes_from_the_file_stem(tmp_path):
    path = _write(tmp_path, "VAR a : boolean;\nLTLSPEC G a;\n", name="my_model.smv")
    fi = import_smv_file(path)

    assert fi.project == "my_model"


# -- real nuXmv example files (tests/fixtures/smvUseCases/) --------------------------------


def test_growing_counter_integer_imports_cleanly():
    fi = import_smv_file(_FIXTURES / "growing-counter-integer.smv")

    by_name = {v.name: v for v in fi.variables}
    assert by_name["state"].type == VariableType.ENUM
    assert by_name["state"].enum_values == ["s0", "s1", "s2", "s3"]
    assert by_name["c"].type == VariableType.INT
    assert by_name["lim"].type == VariableType.FLOAT
    assert "s3" not in by_name  # the enum literal, not a second variable

    assert len(fi.requirements) == 1
    req = fi.requirements[0]
    assert req.ft_formula == "G F (state = s3)"
    assert req.pt_formula == ""
    assert req.variable_names == ["state"]


def test_growing_counter_real_imports_cleanly_with_a_define_in_the_way():
    """DEFINE lim := 5; sits right before the VAR block -- must not be swallowed into it or
    break parsing of the real declarations after it."""
    fi = import_smv_file(_FIXTURES / "growing-counter-real.smv")

    by_name = {v.name: v for v in fi.variables}
    assert set(by_name) == {"state", "c", "x", "delta"}
    assert by_name["x"].type == VariableType.FLOAT
    assert fi.requirements[0].ft_formula == "G F (state = s3)"


def test_krca1p1_real_benchmark_imports_as_one_large_mixed_time_requirement():
    fi = import_smv_file(_FIXTURES / "krca1p1.smv")

    assert len(fi.variables) == 16
    assert all(v.type == VariableType.BOOL for v in fi.variables)
    assert len(fi.requirements) == 1
    req = fi.requirements[0]
    # No trailing ";" in the source file -- confirms the parser doesn't require one.
    assert req.pt_formula  # mixes H/O/S/Y with G/X/U -- goes entirely to pt_formula
    assert req.ft_formula == ""
    assert len(req.variable_names) == 16


def test_arbiter_multi_property_imports_four_separate_named_requirements():
    """krca1p1.smv (and every other file nuXmv ships) has only one LTLSPEC -- this hand-written
    fixture is what actually exercises importing several requirements from one .smv file."""
    fi = import_smv_file(_FIXTURES / "arbiter_multi_property.smv")

    assert [r.reqid for r in fi.requirements] == [
        "mutual_exclusion", "hidden_disjunctive_trigger", "hidden_biconditional_past",
        "typed_variable_comparison",
    ]
    assert fi.requirement("mutual_exclusion").ft_formula == "G (! (out1 & out2))"
    assert fi.requirement("hidden_disjunctive_trigger").ft_formula == "G (((mode = 1) | (mode = 2)) -> alarm)"
    past = fi.requirement("hidden_biconditional_past")
    assert past.pt_formula == "H (alarm <-> ((mode = 1) | (mode = 2)))"  # the file's one H property
    assert past.ft_formula == ""
    assert fi.requirement("typed_variable_comparison").ft_formula == "G ((x = y) -> safe)"


@requires_spot
def test_arbiter_mutual_exclusion_has_no_sound_per_output_split():
    """Negative control: splitting the cross-output coupling into independent per-output rules
    is strictly stronger, not equivalent -- confirms this fixture isn't all easy "just read off
    the &" cases."""
    fi = import_smv_file(_FIXTURES / "arbiter_multi_property.smv")
    req = fi.requirement("mutual_exclusion")
    naive_split = "((G (! out1)) & (G (! out2)))"

    result = _check_tautology_spot(f"({req.ft_formula}) <-> ({naive_split})", fi.variables)

    assert result.status == "not_tautology"


@requires_spot
def test_arbiter_hidden_disjunctive_trigger_has_a_real_but_nonsyntactic_split():
    """True only by distributing the implication over the disjunctive antecedent -- there's no
    "&" anywhere in the original formula to read the split off of."""
    fi = import_smv_file(_FIXTURES / "arbiter_multi_property.smv")
    req = fi.requirement("hidden_disjunctive_trigger")
    sound_split = "((G ((mode = 1) -> alarm)) & (G ((mode = 2) -> alarm)))"

    result = _check_tautology_spot(f"({req.ft_formula}) <-> ({sound_split})", fi.variables)

    assert result.status == "tautology"


@requires_nuxmv
def test_arbiter_hidden_biconditional_past_has_a_real_but_nonsyntactic_split():
    fi = import_smv_file(_FIXTURES / "arbiter_multi_property.smv")
    req = fi.requirement("hidden_biconditional_past")
    sound_split = (
        "((H ((((mode = 1) | (mode = 2))) -> alarm)) & "
        "(H (alarm -> (((mode = 1) | (mode = 2))))))"
    )

    result = _check_tautology_nuxmv(f"({req.pt_formula}) <-> ({sound_split})", fi.variables)

    assert result.status == "tautology"


@requires_spin
def test_arbiter_typed_variable_comparison_validates_through_spins_domain_widening():
    fi = import_smv_file(_FIXTURES / "arbiter_multi_property.smv")
    req = fi.requirement("typed_variable_comparison")

    result = _check_tautology_spin(f"({req.ft_formula}) <-> ({req.ft_formula})", fi.variables)

    assert result.status == "tautology"
