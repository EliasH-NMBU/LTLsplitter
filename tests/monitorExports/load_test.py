#!/usr/bin/env python3
"""Load-tests a generated Ogma/Copilot ROS2 monitor package (LTLsplitter page 4's "Generate
Monitor") by publishing synthetic input data at steadily ramping rates and watching how the
monitor's violation ("handler") topics respond -- looking for the point where it starts falling
behind, not just whether it eventually produces a verdict.

WHY THIS APPROACH (read before changing the methodology):
    Every subscription the generated monitor opens (copilot_monitor.cpp) uses ROS2's default
    QoS: KEEP_LAST with depth 10. Once publishes arrive faster than the node's executor can
    drain them, rclcpp/DDS does NOT queue indefinitely -- it silently drops the oldest queued
    messages. The generated messages (std_msgs::Bool/Int32, no Header, no sequence number)
    carry nothing that would let an outside observer count exactly how many of its own
    publishes were dropped before reaching the monitor's queue, and the monitor's own code
    can't be changed to add instrumentation without it being overwritten the next time it's
    regenerated. So "the queue filled up" isn't observed directly here -- it's inferred from
    one externally-observable symptom instead, computed per rate step below: handler_event_rate_hz
    stops growing roughly in step with the publish rate (or drops) while the publish rate keeps
    climbing -- fewer of the monitor's own evaluations are producing a result than the input
    rate alone would predict. That's not a precise "N messages dropped" count -- it's the same
    kind of external, black-box signal a real deployment would have to rely on too, since
    nothing here can see inside the monitor's own subscription queue.

    An earlier version also recorded a wall-clock timestamp on every single handler event (via
    time.monotonic()) to compute inter-arrival burstiness stats (mean/p95/max gap between
    events) as a second symptom. Dropped in favor of a plain per-topic counter: that second
    symptom was never used by the automated check below, only printed for manual inspection,
    and per-event timestamping is overhead that lives entirely in THIS script's own subscriber
    callbacks, not in the monitor being measured -- if those callbacks ever fell behind their
    own incoming queue (same default depth-10 QoS as everything else here), that would silently
    undercount the monitor's real output and misattribute this script's own bottleneck to the
    monitor's. A plain integer increment carries essentially none of that risk, and costs less
    than the timestamp + list-append it replaced.

Run against the real compiled Group_1/2/3 monitors (ROS 2 Lyrical Luth, colcon-built). Publish
counts match the target rate up to ~3000 Hz. The handler-event saturation signature does show up,
but see MONITOR CPU below: for most groups it's this script's, not the monitor's. One earlier bug this process caught: naming
LoadTestNode's own tracking dicts `self._publishers`/`self._subscriptions`, which collide with
rclpy's own `Node` internals of the same name and crashed `destroy_node()` -- fixed by renaming
to `self._input_publishers`/`self._handler_subscriptions`.

MONITOR CPU (added after Group_3, 2026-11-23): the handler-event count turned out NOT to be a
reliable throughput measure on its own. Sampling per-thread CPU showed this script's own Python
executor thread pinned at ~100% already at 100 Hz for the 13- and 22-requirement groups -- it
can't count more handler events than it can drain, so above that point handler_event_rate_hz
measures this script's ceiling, not the monitor's. Each step therefore also records, from
/proc, the monitor process's CPU (total and busiest thread -- its executor thread, which
saturates first) and the CPU time it spends per step() call, plus this script's own busiest
thread and a tester_saturated flag: when that's true, ignore that step's handler-event columns
and read the monitor CPU columns instead. The monitor is found by process name ("copilot") or
--monitor-pid.

NOMINAL VALUES (--values): random inputs make roughly half of all checks fail, so the monitor's
cost was dominated by publishing violations, and the violation stream overloaded this script's
own subscriber. With --values every round publishes the SAME fixed values (topic=value pairs;
unlisted topics get 0/false), chosen so no requirement is violated -- the load is then pure
evaluation, and handler_events should stay 0 (non-zero means the values aren't actually
nominal for this monitor).

SEVERAL MONITORS AT ONCE (--package-dir repeated): inputs are the union of the packages' input
topics (each published once per round -- every monitor subscribes to the same topic), handlers
are all of them, and the monitor CPU columns cover every running "copilot" process: total is the
sum, busiest thread is the busiest thread of any monitor (the first to saturate), with the
per-monitor busiest threads in monitor_busiest_threads.

Usage (inside the ROS2 environment the monitor itself runs in, e.g. the Dockerfile's
spaceros-user container, with this monitor's "copilot" node already running separately):
    python3 load_test.py --package-dir tests/monitorExports/Group_1 \\
        --rates 10,20,50,100,200,500,1000,2000 --duration 5 --out group1_results.csv

Run once per group (--package-dir Group_1, then again with Group_2) -- each monitor is tested
on its own, not simultaneously, so a result is never a mix of two monitors' saturation points.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import re
import time
from dataclasses import dataclass, fields
from pathlib import Path

# Import failure is handled lazily (raised in main(), not here) so the topic-parsing and
# load-math logic below -- the parts that don't actually need a live ROS2 install -- can still
# be imported and unit-tested on their own (see test_load_test.py, run in the LTLsplitter dev
# sandbox, which has no ROS2 at all).
try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import (
        Bool, Empty, Float32, Float64, Int8, Int16, Int32, Int64, UInt8, UInt16, UInt32, UInt64,
    )
    _ROS2_AVAILABLE = True
except ImportError:
    _ROS2_AVAILABLE = False
    Node = object  # lets `class LoadTestNode(Node)` below still evaluate at import time
    Bool = Empty = Float32 = Float64 = Int8 = Int16 = Int32 = Int64 = UInt8 = UInt16 = UInt32 = UInt64 = None

_MSG_TYPES = {
    "Bool": Bool, "Empty": Empty, "Float32": Float32, "Float64": Float64,
    "Int8": Int8, "Int16": Int16, "Int32": Int32, "Int64": Int64,
    "UInt8": UInt8, "UInt16": UInt16, "UInt32": UInt32, "UInt64": UInt64,
}

_SUBSCRIPTION_RE = re.compile(
    r'create_subscription<std_msgs::msg::(?P<type>\w+)>\(\s*"(?P<topic>[^"]+)"', re.MULTILINE,
)
_PUBLISHER_RE = re.compile(
    r'create_publisher<std_msgs::msg::(?P<type>\w+)>\(\s*"(?P<topic>[^"]+)"', re.MULTILINE,
)


@dataclass
class MonitorInterface:
    """What a generated monitor package's own copilot_monitor.cpp actually subscribes to
    (inputs this script publishes as load) and publishes (handler/violation topics this script
    observes) -- read from the generated source itself, not guessed or hand-entered, so this
    stays correct for whatever requirements a group actually ended up with."""

    inputs: list[tuple[str, str]]  # (topic, std_msgs type name), e.g. ("/sRobotState", "Int32")
    handlers: list[str]            # handler topic names, e.g. "copilot/handlerOperationalstate_1"


def parse_monitor_interface(package_dir: Path) -> MonitorInterface:
    source = package_dir / "copilot" / "src" / "copilot_monitor.cpp"
    if not source.is_file():
        raise FileNotFoundError(
            f"{source} doesn't exist -- --package-dir should point at a directory generated by "
            "LTLsplitter's \"Generate Monitor\" (one with copilot/src/copilot_monitor.cpp in it)."
        )
    text = source.read_text()
    inputs = [
        (m.group("topic"), m.group("type"))
        for m in _SUBSCRIPTION_RE.finditer(text) if m.group("type") != "Empty"
    ]
    handlers = [
        m.group("topic") for m in _PUBLISHER_RE.finditer(text) if m.group("type") == "Empty"
    ]
    if not inputs:
        raise ValueError(f"No input subscriptions found in {source} -- is this really a generated monitor package?")
    return MonitorInterface(inputs=inputs, handlers=handlers)


def _random_value(msg_type_name: str, int_max: int):
    if msg_type_name == "Bool":
        return random.getrandbits(1) == 1
    if msg_type_name in ("Float32", "Float64"):
        return random.uniform(-float(int_max), float(int_max))
    # Biased toward a small range rather than the type's full width: these are typically
    # FRETISH "mode"/"state"/"classifier"-style small enums encoded as ints, and a condition
    # like "state = 2" needs repeated small values to ever actually trigger -- uniform over the
    # full int32 range would make every handler event vanishingly rare and the whole throughput
    # signal this script depends on too sparse to read. Override with --int-max if a system's
    # real integer variables genuinely span a wider range.
    lo = 0 if msg_type_name.startswith("U") else -int_max
    return random.randint(lo, int_max)


def merge_interfaces(interfaces: list[MonitorInterface]) -> MonitorInterface:
    """Several monitors driven together: shared input topics once, every handler topic."""
    inputs: dict[str, str] = {}
    for interface in interfaces:
        for topic, type_name in interface.inputs:
            if inputs.setdefault(topic, type_name) != type_name:
                raise ValueError(f"{topic} has type {inputs[topic]} in one package and {type_name} in another")
    handlers = [h for interface in interfaces for h in interface.handlers]
    return MonitorInterface(inputs=list(inputs.items()), handlers=handlers)


def parse_values(text: str, interface: MonitorInterface) -> dict[str, object]:
    """"--values /classifier=0,/halt=false" -> a fixed value for every input topic; topics not
    listed get 0 / false. Topic names may be given with or without the leading "/"."""
    types = dict(interface.inputs)
    values: dict[str, object] = {topic: (False if t == "Bool" else 0.0 if t.startswith("Float") else 0) for topic, t in types.items()}
    for pair in filter(None, (p.strip() for p in text.split(","))):
        topic, _, raw = pair.partition("=")
        topic = topic.strip() if topic.strip().startswith("/") else "/" + topic.strip()
        if topic not in types:
            # One value list can then serve every group of a system: a monitor generated with
            # only the topics its requirements use simply doesn't subscribe to the others.
            print(f"Note: {topic} isn't an input of this monitor -- not published.")
            continue
        raw, type_name = raw.strip(), types[topic]
        if type_name == "Bool":
            if raw.lower() not in ("true", "false", "1", "0"):
                raise ValueError(f"{topic} is Bool -- use true/false, not {raw!r}")
            values[topic] = raw.lower() in ("true", "1")
        elif type_name.startswith("Float"):
            values[topic] = float(raw)
        else:
            values[topic] = int(raw)
    return values


class LoadTestNode(Node):
    def __init__(self, interface: MonitorInterface, int_max: int, fixed_values: dict[str, object] | None = None):
        super().__init__("monitor_load_test")
        self._int_max = int_max
        self._input_types = dict(interface.inputs)
        self._fixed_messages = None
        if fixed_values is not None:
            # Built once and re-published every round: the values never change, and building
            # them per round would only add this script's own overhead.
            self._fixed_messages = {}
            for topic, type_name in interface.inputs:
                msg = _MSG_TYPES[type_name]()
                msg.data = fixed_values[topic]
                self._fixed_messages[topic] = msg
        # Named _input_publishers/_handler_subscriptions, not _publishers/_subscriptions --
        # confirmed the hard way (a real run against a real node) that those two names collide
        # with rclpy's own Node bookkeeping of the same names: this still publishes/subscribes
        # fine day to day, since nothing reads rclpy's internal copies during normal operation,
        # but destroy_node() reads its own _publishers expecting its own bookkeeping and crashes
        # (KeyError) once this subclass has silently replaced it.
        self._input_publishers = {
            topic: self.create_publisher(_MSG_TYPES[type_name], topic, 10)
            for topic, type_name in interface.inputs
        }
        # A plain per-topic counter, not a timestamp log -- see the module docstring's "An
        # earlier version..." paragraph for why: this is deliberately the cheapest possible
        # callback, so this script's own subscriber-side processing is as unlikely as possible
        # to become the bottleneck being measured.
        self._handler_counts: dict[str, int] = {h: 0 for h in interface.handlers}
        self._handler_subscriptions = [
            self.create_subscription(Empty, topic, self._make_handler_callback(topic), 10)
            for topic in interface.handlers
        ]

    def _make_handler_callback(self, topic: str):
        def _callback(_msg) -> None:
            self._handler_counts[topic] += 1
        return _callback

    def publish_one_round(self) -> None:
        """Publishes one fresh value to every input topic -- "one round" is the unit the
        requested rate is measured in, matching how the monitor's own step() function re-
        evaluates every property on every single variable update regardless of which variable
        changed."""
        if self._fixed_messages is not None:
            for topic, publisher in self._input_publishers.items():
                publisher.publish(self._fixed_messages[topic])
            return
        for topic, publisher in self._input_publishers.items():
            msg_type = _MSG_TYPES[self._input_types[topic]]
            msg = msg_type()
            msg.data = _random_value(self._input_types[topic], self._int_max)
            publisher.publish(msg)

    def handler_counts(self) -> dict[str, int]:
        return self._handler_counts

    def reset_handler_counts(self) -> None:
        for topic in self._handler_counts:
            self._handler_counts[topic] = 0


@dataclass
class StepResult:
    target_rate_hz: float
    """A "round" rate, NOT a message rate -- see run_rate_step's docstring. One round publishes
    one fresh value to every input topic, so the real message rate is round_rate * num_inputs,
    and the real requirement-check rate (every requirement is re-evaluated on every single
    message, confirmed in copilot_monitor.cpp: each variable's own callback calls step()) is
    round_rate * num_inputs * num_requirements -- see requirement_checks_per_sec below."""
    actual_rate_hz: float
    published: int
    requirement_checks_per_sec: float
    handler_events: int
    handler_event_rate_hz: float
    monitor_cpu_pct: float | None = None
    """The monitor process's CPU over the step, in % of one core (all threads)."""
    monitor_busiest_thread_pct: float | None = None
    """Its busiest thread -- the executor thread running every callback and step(); ~100% means
    the monitor is saturated."""
    monitor_cpu_us_per_step: float | None = None
    """Monitor CPU time per step() call (published rounds x input topics), in microseconds --
    the per-message cost, comparable across groups with different requirement counts."""
    monitor_busiest_threads: str = ""
    """With several monitors: each one's busiest thread %, in --package-dir order."""
    tester_busiest_thread_pct: float | None = None
    tester_saturated: bool | None = None
    """True when this script's own executor thread was >= 90% busy: its handler-event count for
    this step is then a lower bound, not a measurement."""


_TESTER_SATURATED_PCT = 90.0


def _thread_cpu_ticks(pid: int) -> dict[str, int]:
    """utime + stime per thread of `pid`, from /proc (Linux only)."""
    ticks = {}
    task_dir = Path(f"/proc/{pid}/task")
    for tid in os.listdir(task_dir):
        try:
            fields_ = (task_dir / tid / "stat").read_text().rsplit(")", 1)[1].split()
        except OSError:
            continue
        ticks[tid] = int(fields_[11]) + int(fields_[12])
    return ticks


def _cpu_pcts(before: dict[str, int], after: dict[str, int], seconds: float) -> tuple[float, float]:
    """(total %, busiest thread %) of one core over `seconds`."""
    hz = os.sysconf("SC_CLK_TCK")
    per_thread = [(after[t] - before.get(t, 0)) / hz / seconds * 100 for t in after]
    return sum(per_thread), max(per_thread, default=0.0)


def find_monitor_pids(name: str = "copilot") -> list[int]:
    """Every running monitor's pid, by process name (the generated node's executable is called
    "copilot"), oldest first."""
    matches = []
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            try:
                if Path(f"/proc/{entry}/comm").read_text().strip() == name:
                    matches.append(int(entry))
            except OSError:
                pass
    return sorted(matches)


def run_rate_step(
    node: LoadTestNode, rate_hz: float, duration_s: float, num_inputs: int, num_requirements: int,
    monitor_pids: list[int] = (),
) -> StepResult:
    """Publishes one round per 1/rate_hz seconds for duration_s seconds, spinning the node's
    executor between publishes so handler callbacks are processed as they arrive rather than
    only in a batch at the end (which would make this script's own queue the bottleneck instead
    of the monitor's -- see the module docstring).

    "One round" = one fresh value sent to each of num_inputs topics, each of which independently
    triggers a step() call on the monitor side (confirmed in copilot_monitor.cpp: every
    variable's callback calls step()), and each step() call re-evaluates every one of
    num_requirements registered properties at once. So the actual load on the monitor is
    num_inputs * num_requirements times higher than the round rate alone suggests -- that's
    requirement_checks_per_sec in the result, not just actual_rate_hz."""
    node.reset_handler_counts()
    monitor_before = [_thread_cpu_ticks(pid) for pid in monitor_pids]
    tester_before = _thread_cpu_ticks(os.getpid())
    started = time.monotonic()
    interval = 1.0 / rate_hz
    deadline = time.monotonic() + duration_s
    published = 0
    next_publish = time.monotonic()
    while True:
        now = time.monotonic()
        if now >= deadline:
            break
        if now >= next_publish:
            node.publish_one_round()
            published += 1
            next_publish += interval
        rclpy.spin_once(node, timeout_sec=max(0.0, min(next_publish - now, deadline - now)))

    total_handler_events = sum(node.handler_counts().values())
    elapsed = time.monotonic() - started
    _tester_total, tester_busiest = _cpu_pcts(tester_before, _thread_cpu_ticks(os.getpid()), elapsed)
    monitor_total = monitor_busiest = monitor_us_per_step = None
    per_monitor_busiest: list[float] = []
    if monitor_pids:
        per_monitor = [_cpu_pcts(before, _thread_cpu_ticks(pid), elapsed) for pid, before in zip(monitor_pids, monitor_before)]
        monitor_total = sum(total for total, _ in per_monitor)
        per_monitor_busiest = [busiest for _, busiest in per_monitor]
        monitor_busiest = max(per_monitor_busiest)
        steps = published * num_inputs
        monitor_us_per_step = monitor_total / 100 * elapsed / steps * 1e6 if steps else None
    actual_rate_hz = published / duration_s
    return StepResult(
        target_rate_hz=rate_hz,
        actual_rate_hz=actual_rate_hz,
        published=published,
        requirement_checks_per_sec=actual_rate_hz * num_inputs * num_requirements,
        handler_events=total_handler_events,
        handler_event_rate_hz=total_handler_events / duration_s,
        monitor_cpu_pct=None if monitor_total is None else round(monitor_total, 1),
        monitor_busiest_thread_pct=None if monitor_busiest is None else round(monitor_busiest, 1),
        monitor_cpu_us_per_step=None if monitor_us_per_step is None else round(monitor_us_per_step, 2),
        monitor_busiest_threads=" ".join(f"{b:.1f}" for b in per_monitor_busiest),
        tester_busiest_thread_pct=round(tester_busiest, 1),
        tester_saturated=tester_busiest >= _TESTER_SATURATED_PCT,
    )


def _print_saturation_hint(results: list[StepResult]) -> None:
    """A heuristic pointer at where to look, not a verdict -- flags the first rate step where
    handler-event throughput grew much more slowly than the publish rate did (or fell outright)
    compared to the step before it, which is the signature described at the top of this file."""
    flagged = False
    for prev, cur in zip(results, results[1:]):
        rate_growth = cur.actual_rate_hz - prev.actual_rate_hz
        if rate_growth <= 0:
            continue
        event_growth = cur.handler_event_rate_hz - prev.handler_event_rate_hz
        ratio = event_growth / rate_growth
        if ratio < 0.2 * max(prev.handler_event_rate_hz / max(prev.actual_rate_hz, 1e-9), 1e-9):
            print(
                f"\nPossible saturation between {prev.actual_rate_hz:.0f} Hz and "
                f"{cur.actual_rate_hz:.0f} Hz: handler-event rate grew by only {event_growth:.2f}/s "
                f"while the publish rate grew by {rate_growth:.2f}/s."
            )
            flagged = True
    if not flagged:
        print("\nNo clear saturation signature in this rate range -- try higher rates.")


def main() -> None:
    if not _ROS2_AVAILABLE:
        raise SystemExit(
            "rclpy / std_msgs aren't importable -- this has to run inside a ROS2 environment "
            "(source the workspace's setup.bash first), not wherever this was just invoked from."
        )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package-dir", required=True, type=Path, action="append", help="A generated monitor package directory, e.g. tests/monitorExports/Group_1 -- repeat it to drive several running monitors at once")
    parser.add_argument("--values", default=None, help="Publish these fixed nominal values every round instead of random ones, e.g. \"/classifier=0,/state=0,/distance_to_target=10\" (unlisted topics: 0/false)")
    parser.add_argument("--rates", default="10,20,50,100,200,500,1000,2000", help="Comma-separated target publish rates (Hz) to ramp through")
    parser.add_argument("--duration", type=float, default=5.0, help="Seconds to hold each rate step")
    parser.add_argument("--settle", type=float, default=1.0, help="Seconds to pause between rate steps")
    parser.add_argument("--int-max", type=int, default=5, help="Int topics are randomized over roughly [-int_max, int_max] (or [0, int_max] for unsigned) -- see _random_value's docstring for why this defaults small")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None, help="CSV file to write per-step results to")
    parser.add_argument("--monitor-pid", type=int, action="append", default=None, help="A running monitor's pid, for the CPU columns (repeatable; default: every process named \"copilot\")")
    args = parser.parse_args()
    monitor_pids = args.monitor_pid or find_monitor_pids()
    if len(monitor_pids) != len(args.package_dir):
        print(
            f"Found {len(monitor_pids)} monitor process(es) for {len(args.package_dir)} package(s) -- "
            "pass --monitor-pid for each; monitor CPU columns may not match the packages."
        )

    random.seed(args.seed)
    interface = merge_interfaces([parse_monitor_interface(d) for d in args.package_dir])
    print(
        f"Discovered {len(interface.inputs)} input topic(s) and {len(interface.handlers)} "
        f"handler topic(s) in {', '.join(map(str, args.package_dir))}"
    )
    fixed_values = parse_values(args.values, interface) if args.values is not None else None
    if fixed_values is not None:
        print("Publishing fixed nominal values every round: " + ", ".join(f"{t}={v}" for t, v in fixed_values.items()))

    rclpy.init()
    node = LoadTestNode(interface, args.int_max, fixed_values)
    results: list[StepResult] = []
    try:
        for rate in (float(r) for r in args.rates.split(",")):
            print(f"\n--- target rate: {rate:g} Hz ---")
            result = run_rate_step(node, rate, args.duration, len(interface.inputs), len(interface.handlers), monitor_pids)
            results.append(result)
            print(
                f"published={result.published} rounds ({result.actual_rate_hz:.1f}Hz) = "
                f"{result.requirement_checks_per_sec:.0f} requirement-checks/s  "
                f"handler_events={result.handler_events} ({result.handler_event_rate_hz:.1f}/s)"
            )
            if result.monitor_cpu_pct is not None:
                print(
                    f"monitor CPU {result.monitor_cpu_pct:.0f}% (busiest thread "
                    f"{result.monitor_busiest_thread_pct:.0f}%), {result.monitor_cpu_us_per_step:.2f} us/step"
                )
            if result.tester_saturated:
                print(f"tester saturated ({result.tester_busiest_thread_pct:.0f}%) -- handler events are a lower bound")
            time.sleep(args.settle)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    if args.out:
        with args.out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[field.name for field in fields(StepResult)])
            writer.writeheader()
            for r in results:
                writer.writerow(r.__dict__)
        print(f"\nWrote {len(results)} row(s) to {args.out}")

    if fixed_values is None:
        _print_saturation_hint(results)
    elif any(r.handler_events for r in results):
        print("\nWARNING: violations were reported -- these values aren't nominal for this monitor.")
    else:
        print("\nNo violations at any rate: the values are nominal; read the monitor CPU columns for load.")
    short = [r for r in results if r.actual_rate_hz < 0.95 * r.target_rate_hz]
    if short:
        print("Publish rate fell short of the target at " + ", ".join(f"{r.target_rate_hz:g} Hz" for r in short)
              + " -- this script's publishing limit, not the monitor's.")


if __name__ == "__main__":
    main()
