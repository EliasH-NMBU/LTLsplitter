"""Smoke tests against real FRET project exports -- NASA's own case studies, not hand-written
fixtures -- to catch import bugs the synthetic sRobot fixture's narrow formula shapes never
would. Downloaded from https://github.com/NASA-SW-VnV/fret (Apache 2.0), under caseStudies/:

- fsm_reqts_and_vars.json          -- FiniteStateMachine
- LPC_full_reqts_and_vars.json     -- LiftPlusCruise (full)
- LPC_mini_reqts_and_vars.json     -- LiftPlusCruise (mini)
- LM_reqts_and_vars.json           -- LiquidMixer

(caseStudies/LMCPS/LM_requirements.json was tried too but isn't a FRET requirements/variables
export at all -- its "variables" array holds Simulink/CoCoSim modeldoc metadata, a different
export pipeline entirely. Not included.)

Importing these surfaced a real crash: some of these files' variable dataType/idType fields are
wrapped in a single-element list (e.g. ["double"]) instead of a bare string -- confirmed in both
the FiniteStateMachine and LiquidMixer files, not hypothetical -- which raised TypeError (list is
unhashable) when used as a dict key. Fixed via `_normalize_type_field` in fret_import.py; these
tests guard against that regressing.

Known gap these examples surfaced (not fixed here -- out of scope for "add test fixtures"):
Kind2's past-time translation (`_strip_top_level_h`/`_build_lustre_contract` in kind2_check.py)
only handles a single top-level H wrapping an otherwise-*propositional* body -- no translation
for nested Y/O/S/Z operators. The sRobot fixture happens to never use them, but most real FRET
specs do -- confirmed here: LPC_full uses Y/O/Z inside the H-body in 50 of 57 requirements, and
every LiquidMixer requirement uses Z. For those, `_build_lustre_contract` would pass the
untranslated operator straight into the generated Lustre text, which Kind2 would then reject as
invalid syntax. This is a real, demonstrated limitation of the current Kind2 integration, not
exercised by a test here since fixing it is a substantial translation effort of its own.
"""

from pathlib import Path

from ltlsplitter.core.fret_import import import_fret_file
from ltlsplitter.core.models import VariableType

_FIXTURES = Path(__file__).parent / "fixtures"


def test_finite_state_machine_imports_cleanly():
    """Regression test for the list-wrapped dataType crash -- SENSTATE/STATE/etc. in this file
    have dataType: ["double"] rather than "double"."""
    fi = import_fret_file(_FIXTURES / "fsm_reqts_and_vars.json")

    assert fi.project == "FSM"
    assert len(fi.requirements) == 13
    assert len(fi.variables) == 35
    assert len(fi.leaf_requirements()) == 13  # none of these are split -- every one is a leaf


def test_liquid_mixer_imports_cleanly():
    """Same list-wrapped dataType shape as the FSM file, confirmed independently here --
    this one also has every variable's idType as None rather than a string, which must not
    crash either (falls back to the INPUT default, same as a genuinely-unset idType)."""
    fi = import_fret_file(_FIXTURES / "LM_reqts_and_vars.json")

    assert fi.project == "Liquid_mixer"
    assert len(fi.requirements) == 12
    assert len(fi.variables) == 24
    assert all(v.type == VariableType.BOOL for v in fi.variables)


def test_lift_plus_cruise_full_imports_cleanly():
    fi = import_fret_file(_FIXTURES / "LPC_full_reqts_and_vars.json")

    assert fi.project == "LPC"
    assert len(fi.requirements) == 57
    assert len(fi.variables) == 13
    # unlike the sRobot fixture, real variety: float-typed variables, and several genuine
    # assumption-named requirements -- both worth having in a fixture set.
    assert VariableType.FLOAT in {v.type for v in fi.variables}
    assert any(r.is_assumption for r in fi.requirements)


def test_lift_plus_cruise_mini_imports_cleanly():
    fi = import_fret_file(_FIXTURES / "LPC_mini_reqts_and_vars.json")

    assert fi.project == "LPC_mini"
    assert len(fi.requirements) == 19
    assert len(fi.variables) == 8


def test_lift_plus_cruise_requirements_reference_declared_variables():
    """A basic end-to-end sanity check beyond "doesn't crash": every variable name a requirement
    claims to reference must actually be a declared variable -- catches a subtler parsing bug
    (e.g. mis-splitting an identifier list) that a bare import wouldn't."""
    fi = import_fret_file(_FIXTURES / "LPC_full_reqts_and_vars.json")
    declared = {v.name for v in fi.variables}

    for req in fi.requirements:
        assert set(req.variable_names) <= declared, f"{req.reqid} references undeclared variable(s)"
