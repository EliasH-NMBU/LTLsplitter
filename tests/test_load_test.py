"""Tests for monitorExports/load_test.py's pure-Python parts (topic/type discovery and the
load-math/reporting logic) -- the parts that don't need a live ROS2 install, which is what makes
this test file able to run inside the plain LTLsplitter dev environment. The rclpy-dependent
parts (LoadTestNode, run_rate_step, main) are NOT exercised here -- they're covered separately,
against a real ROS 2 install and the real compiled "copilot" monitor (see the script's own
VALIDATED note at the top of load_test.py for what that confirmed, including a real bug it
caught)."""

import csv
import importlib.util
import random
import sys
from dataclasses import fields
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parent / "monitorExports" / "load_test.py"
_FIXTURES = Path(__file__).parent / "monitorExports"


def _load_module():
    spec = importlib.util.spec_from_file_location("ltlsplitter_monitor_load_test", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    # dataclasses (used throughout load_test.py, which has `from __future__ import annotations`)
    # resolves string type annotations via sys.modules[cls.__module__] -- registering here first
    # is required, or that lookup returns None and dataclass() crashes on the first field access.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def load_test():
    return _load_module()


def _step_result(load_test_module, **overrides):
    """Builds a StepResult with sensible defaults, overridden per test -- keyword-only so these
    tests don't break every time a field is added to StepResult (confirmed this isn't
    hypothetical: adding requirement_checks_per_sec broke every positionally-built one here)."""
    defaults = dict(
        target_rate_hz=10.0, actual_rate_hz=10.0, published=50, requirement_checks_per_sec=4550.0,
        handler_events=40, handler_event_rate_hz=8.0,
    )
    defaults.update(overrides)
    return load_test_module.StepResult(**defaults)


def test_module_imports_without_a_ros2_install(load_test):
    assert load_test._ROS2_AVAILABLE is False


def test_parses_group_1_real_generated_package(load_test):
    iface = load_test.parse_monitor_interface(_FIXTURES / "Group_1")

    assert len(iface.inputs) == 7
    assert all(t in ("Bool", "Int32") for _topic, t in iface.inputs)
    assert ("/sRobotState", "Int32") in iface.inputs
    assert len(iface.handlers) == 13
    assert all(h.startswith("copilot/handler") for h in iface.handlers)


def test_parses_group_2_real_generated_package(load_test):
    iface = load_test.parse_monitor_interface(_FIXTURES / "Group_2")

    assert len(iface.inputs) == 7
    assert len(iface.handlers) == 9


def test_missing_package_raises_a_clear_error(load_test, tmp_path):
    with pytest.raises(FileNotFoundError, match="Generate Monitor"):
        load_test.parse_monitor_interface(tmp_path)


def test_random_value_bool_produces_both_values(load_test):
    random.seed(0)
    values = {load_test._random_value("Bool", 5) for _ in range(100)}
    assert values == {True, False}


def test_random_value_int_stays_within_the_requested_range(load_test):
    random.seed(0)
    values = [load_test._random_value("Int32", 5) for _ in range(500)]
    assert min(values) >= -5
    assert max(values) <= 5


def test_random_value_unsigned_int_is_never_negative(load_test):
    random.seed(0)
    values = [load_test._random_value("UInt8", 5) for _ in range(500)]
    assert min(values) >= 0


def test_saturation_hint_flags_a_flatlining_handler_rate(load_test, capsys):
    """Publish rate jumps 100x but the handler-event rate barely moves -- the monitor isn't
    keeping up with the extra load."""
    healthy = _step_result(load_test)
    flatlined = _step_result(
        load_test, target_rate_hz=1000, actual_rate_hz=1000, published=5000,
        requirement_checks_per_sec=455000, handler_events=42, handler_event_rate_hz=8.4,
    )

    load_test._print_saturation_hint([healthy, flatlined])

    assert "Possible saturation" in capsys.readouterr().out


def test_saturation_hint_does_not_flag_proportional_scaling(load_test, capsys):
    healthy_low = _step_result(load_test)
    healthy_high = _step_result(
        load_test, target_rate_hz=100, actual_rate_hz=100, published=500,
        requirement_checks_per_sec=45500, handler_events=400, handler_event_rate_hz=80,
    )

    load_test._print_saturation_hint([healthy_low, healthy_high])

    assert "No clear saturation" in capsys.readouterr().out


def test_step_results_round_trip_through_csv(load_test, tmp_path):
    result = _step_result(load_test)
    out = tmp_path / "out.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[field.name for field in fields(load_test.StepResult)])
        writer.writeheader()
        writer.writerow(result.__dict__)

    rows = list(csv.DictReader(out.open()))

    assert rows[0]["handler_events"] == "40"
    assert rows[0]["requirement_checks_per_sec"] == "4550.0"


def test_main_fails_clearly_without_ros2(load_test, monkeypatch):
    monkeypatch.setattr("sys.argv", ["load_test.py", "--package-dir", str(_FIXTURES / "Group_1")])
    with pytest.raises(SystemExit, match="ROS2 environment"):
        load_test.main()


def test_parse_values_fills_unlisted_topics_with_zero_or_false():
    lt = _load_module()
    interface = lt.MonitorInterface(inputs=[("/state", "Int32"), ("/halt", "Bool"), ("/speed", "Float64")], handlers=[])

    values = lt.parse_values("state=2, /halt=true", interface)

    assert values == {"/state": 2, "/halt": True, "/speed": 0.0}


def test_parse_values_rejects_unknown_topics_and_bad_booleans():
    import pytest

    lt = _load_module()
    interface = lt.MonitorInterface(inputs=[("/halt", "Bool")], handlers=[])
    with pytest.raises(ValueError, match="isn't an input"):
        lt.parse_values("/nope=1", interface)
    with pytest.raises(ValueError, match="true/false"):
        lt.parse_values("/halt=2", interface)


def test_merge_interfaces_shares_inputs_and_keeps_every_handler():
    lt = _load_module()
    merged = lt.merge_interfaces([
        lt.parse_monitor_interface(_FIXTURES / "Group_1"),
        lt.parse_monitor_interface(_FIXTURES / "Group_2"),
    ])
    assert len(merged.inputs) == 7
    assert len(merged.handlers) == 22
