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
    two externally-observable symptoms instead, both computed per rate step below:
      1. handler_event_rate_hz stops growing roughly in step with the publish rate (or drops)
         while the publish rate keeps climbing -- fewer of the monitor's own evaluations are
         producing a result than the input rate alone would predict.
      2. the gaps between consecutive handler events get bursty (rising p95/max inter-arrival
         time versus the mean) -- a sign the executor is processing messages in backlog bursts
         rather than keeping pace.
    Neither is a precise "N messages dropped" count. Both are the same kind of external,
    black-box signal a real deployment would have to rely on too, since nothing here can see
    inside the monitor's own subscription queue.

VALIDATED: once ROS 2 (Lyrical Luth) was actually installed, this was run end to end against a
real rclpy node (a throwaway stand-in publishing on one of Group_1's real handler topics) at
several rates, including a zero-handler-events case -- publish counts matched the target rate
exactly every time, and it shut down and wrote its CSV cleanly. That run caught one real bug,
now fixed: LoadTestNode originally named its own tracking dicts `self._publishers`/
`self._subscriptions`, which silently collide with rclpy's own `Node` internals of the same
name -- publishing/subscribing worked fine, but `destroy_node()` crashed with a `KeyError`
reading what it expected to be its own bookkeeping. It still has NOT been run against the real
compiled "copilot" monitor (the Haskell/colcon toolchain that builds it isn't set up here) --
sanity-check the first rate step's output against a real monitor (in the same Docker/screen
session as the "Copilot RV" pane -- see ../screenrc) before trusting a full run there.

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
import random
import re
import statistics
import time
from dataclasses import dataclass, field, fields
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


@dataclass
class _HandlerStats:
    count: int = 0
    timestamps: list[float] = field(default_factory=list)


class LoadTestNode(Node):
    def __init__(self, interface: MonitorInterface, int_max: int):
        super().__init__("monitor_load_test")
        self._int_max = int_max
        self._input_types = dict(interface.inputs)
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
        self._handler_stats: dict[str, _HandlerStats] = {h: _HandlerStats() for h in interface.handlers}
        self._handler_subscriptions = [
            self.create_subscription(Empty, topic, self._make_handler_callback(topic), 10)
            for topic in interface.handlers
        ]

    def _make_handler_callback(self, topic: str):
        def _callback(_msg) -> None:
            stats = self._handler_stats[topic]
            stats.count += 1
            stats.timestamps.append(time.monotonic())
        return _callback

    def publish_one_round(self) -> None:
        """Publishes one fresh value to every input topic -- "one round" is the unit the
        requested rate is measured in, matching how the monitor's own step() function re-
        evaluates every property on every single variable update regardless of which variable
        changed."""
        for topic, publisher in self._input_publishers.items():
            msg_type = _MSG_TYPES[self._input_types[topic]]
            msg = msg_type()
            msg.data = _random_value(self._input_types[topic], self._int_max)
            publisher.publish(msg)

    def handler_stats(self) -> dict[str, _HandlerStats]:
        return self._handler_stats

    def reset_handler_stats(self) -> None:
        for stats in self._handler_stats.values():
            stats.count = 0
            stats.timestamps.clear()


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
    mean_inter_arrival_ms: float | None
    p95_inter_arrival_ms: float | None
    max_inter_arrival_ms: float | None


def run_rate_step(
    node: LoadTestNode, rate_hz: float, duration_s: float, num_inputs: int, num_requirements: int,
) -> StepResult:
    """Publishes one round per 1/rate_hz seconds for duration_s seconds, spinning the node's
    executor between publishes so handler callbacks are processed as soon as they arrive rather
    than only in a batch at the end (which would distort the inter-arrival timings below).

    "One round" = one fresh value sent to each of num_inputs topics, each of which independently
    triggers a step() call on the monitor side (confirmed in copilot_monitor.cpp: every
    variable's callback calls step()), and each step() call re-evaluates every one of
    num_requirements registered properties at once. So the actual load on the monitor is
    num_inputs * num_requirements times higher than the round rate alone suggests -- that's
    requirement_checks_per_sec in the result, not just actual_rate_hz."""
    node.reset_handler_stats()
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

    all_timestamps = sorted(ts for stats in node.handler_stats().values() for ts in stats.timestamps)
    total_handler_events = len(all_timestamps)
    gaps_ms = [(b - a) * 1000.0 for a, b in zip(all_timestamps, all_timestamps[1:])]
    actual_rate_hz = published / duration_s
    return StepResult(
        target_rate_hz=rate_hz,
        actual_rate_hz=actual_rate_hz,
        published=published,
        requirement_checks_per_sec=actual_rate_hz * num_inputs * num_requirements,
        handler_events=total_handler_events,
        handler_event_rate_hz=total_handler_events / duration_s,
        mean_inter_arrival_ms=statistics.mean(gaps_ms) if gaps_ms else None,
        p95_inter_arrival_ms=(statistics.quantiles(gaps_ms, n=20)[18] if len(gaps_ms) >= 20 else None),
        max_inter_arrival_ms=max(gaps_ms) if gaps_ms else None,
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
                f"while the publish rate grew by {rate_growth:.2f}/s. Check inter-arrival p95/max "
                "around this step too."
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
    parser.add_argument("--package-dir", required=True, type=Path, help="A generated monitor package directory, e.g. tests/monitorExports/Group_1")
    parser.add_argument("--rates", default="10,20,50,100,200,500,1000,2000", help="Comma-separated target publish rates (Hz) to ramp through")
    parser.add_argument("--duration", type=float, default=5.0, help="Seconds to hold each rate step")
    parser.add_argument("--settle", type=float, default=1.0, help="Seconds to pause between rate steps")
    parser.add_argument("--int-max", type=int, default=5, help="Int topics are randomized over roughly [-int_max, int_max] (or [0, int_max] for unsigned) -- see _random_value's docstring for why this defaults small")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None, help="CSV file to write per-step results to")
    args = parser.parse_args()

    random.seed(args.seed)
    interface = parse_monitor_interface(args.package_dir)
    print(
        f"Discovered {len(interface.inputs)} input topic(s) and {len(interface.handlers)} "
        f"handler topic(s) in {args.package_dir}"
    )

    rclpy.init()
    node = LoadTestNode(interface, args.int_max)
    results: list[StepResult] = []
    try:
        for rate in (float(r) for r in args.rates.split(",")):
            print(f"\n--- target rate: {rate:g} Hz ---")
            result = run_rate_step(node, rate, args.duration, len(interface.inputs), len(interface.handlers))
            results.append(result)
            print(
                f"published={result.published} rounds ({result.actual_rate_hz:.1f}Hz) = "
                f"{result.requirement_checks_per_sec:.0f} requirement-checks/s  "
                f"handler_events={result.handler_events} ({result.handler_event_rate_hz:.1f}/s)  "
                f"inter-arrival mean={result.mean_inter_arrival_ms}ms p95={result.p95_inter_arrival_ms}ms "
                f"max={result.max_inter_arrival_ms}ms"
            )
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

    _print_saturation_hint(results)


if __name__ == "__main__":
    main()
