"""Violation response-time probe for the generated Copilot monitors.

Per sample: (re)start the monitor processes, wait for discovery, let them run under whatever
background load is running for WARMUP seconds, publish a nominal round, time a few ROS 2 pings
(one hop: probe -> probe self-subscription; two hops: probe -> C++ relay -> probe, the same
receive-then-publish-Empty path as a monitor minus step()), then publish ONE violating value and
time until the first message on that requirement's handler topic. Then kill the monitors: every
requirement is PTLTL.alwaysBeen, so once violated the handler fires on every step and only the
first message after the violation is a clean measurement.

Samples alternate between two probes:
  halt  -- halt=true while state=0 violates operationalstate_0_2 (a Group 1 requirement)
  class -- classifier=1 at distance 10 violates state_req101    (a Group 2 requirement)
"""
from __future__ import annotations

import argparse
import csv
import os
import signal
import subprocess
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Empty, Int32

TOPICS = {
    "g3": dict(alert="/alert", classifier="/classifier", distance="/distance_to_target",
               halt="/halt", slowdown="/slowdown", state="/state", turnoffUVC="/turnoffUVC"),
    "sr": dict(alert="/sRobotAlert", classifier="/sRobotClassifier", distance="/scan",
               halt="/sRobotHalt", slowdown="/sRobotSlowdown", state="/sRobotState",
               turnoffUVC="/sRobotTurnoffUVC"),
}
NOMINAL = dict(alert=False, classifier=0, distance=10, halt=False, slowdown=False, state=0,
               turnoffUVC=False)
PROBES = {
    "halt": ("halt", True, "copilot/handlerOperationalstate_0_2"),
    "class": ("classifier", 1, "copilot/handlerState_req101"),
}
CONFIGS = {  # config -> (topic naming, monitor workspaces)
    "g3": ("g3", ["g3"]),
    "g12": ("sr", ["g1", "g2"]),
    "g1s2s": ("sr", ["g1s", "g2s"]),
}


def now_ns() -> int:
    return time.monotonic_ns()


class Probe(Node):
    def __init__(self, naming: str):
        super().__init__("violation_probe")
        self.topics = TOPICS[naming]
        self.pubs = {}
        for key, topic in self.topics.items():
            mtype = Bool if isinstance(NOMINAL[key], bool) else Int32
            self.pubs[key] = self.create_publisher(mtype, topic, 10)
        self.handler_rx: dict[str, int | None] = {}
        self.handler_subs = {}
        for _, _, handler in PROBES.values():
            self.handler_rx[handler] = None
            self.handler_subs[handler] = self.create_subscription(
                Empty, handler, lambda _m, h=handler: self._on_handler(h), 10)
        self.ping_pub = self.create_publisher(Bool, "/probe_ping", 10)
        self.one_hop_rx: int | None = None
        self.two_hop_rx: int | None = None
        self.create_subscription(Bool, "/probe_ping", self._on_self_ping, 10)
        self.create_subscription(Empty, "/probe_pong", self._on_pong, 10)

    def _on_handler(self, handler: str) -> None:
        if self.handler_rx[handler] is None:
            self.handler_rx[handler] = now_ns()

    def _on_self_ping(self, _m) -> None:
        if self.one_hop_rx is None:
            self.one_hop_rx = now_ns()

    def _on_pong(self, _m) -> None:
        if self.two_hop_rx is None:
            self.two_hop_rx = now_ns()

    def publish(self, key: str, value) -> None:
        msg = Bool() if isinstance(NOMINAL[key], bool) else Int32()
        msg.data = value
        self.pubs[key].publish(msg)

    def spin_for(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            rclpy.spin_once(self, timeout_sec=0.005)

    def spin_until(self, cond, timeout: float) -> bool:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return True
            rclpy.spin_once(self, timeout_sec=0.0005)
        return cond()

    def ping(self, timeout: float = 0.5) -> tuple[float | None, float | None]:
        self.one_hop_rx = self.two_hop_rx = None
        t0 = now_ns()
        self.ping_pub.publish(Bool(data=True))
        self.spin_until(lambda: self.one_hop_rx is not None and self.two_hop_rx is not None, timeout)
        one = (self.one_hop_rx - t0) / 1e3 if self.one_hop_rx else None
        two = (self.two_hop_rx - t0) / 1e3 if self.two_hop_rx else None
        return one, two


def start_monitor(ws: str) -> subprocess.Popen:
    exe = f"/tmp/{ws}_build_ws/install/copilot/lib/copilot/copilot"
    cmd = f"source /tmp/{ws}_build_ws/install/setup.bash && exec {exe}"
    return subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def stop(procs: list[subprocess.Popen]) -> None:
    """SIGINT first so rclcpp shuts the DDS participant down cleanly (a SIGKILLed participant
    leaves its transport state behind, which degraded later samples); SIGKILL only if it hangs."""
    for p in procs:
        try:
            os.killpg(p.pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    for p in procs:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=CONFIGS, required=True)
    ap.add_argument("--load", type=int, required=True, help="background rounds/s (label only)")
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--warmup", type=float, default=1.0)
    ap.add_argument("--pings", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    naming, workspaces = CONFIGS[args.config]
    rclpy.init()
    node = Probe(naming)
    rows = []
    try:
        for k in range(args.samples):
            probe = "halt" if k % 2 == 0 else "class"
            key, bad_value, handler = PROBES[probe]
            procs = [start_monitor(ws) for ws in workspaces]
            ok = node.spin_until(
                lambda: node.pubs[key].get_subscription_count() >= 1
                and node.handler_subs[handler].get_publisher_count() >= 1
                and node.ping_pub.get_subscription_count() >= 2, 15.0)
            if not ok:
                print(f"sample {k}: discovery timed out", flush=True)
                stop(procs)
                continue
            node.spin_for(args.warmup)
            for nk, nv in NOMINAL.items():  # make sure distance=10 / state=0 have been seen
                node.publish(nk, nv)
            node.spin_for(0.1)
            pings = [node.ping() for _ in range(args.pings)]
            node.spin_for(0.05)
            for h in node.handler_rx:
                node.handler_rx[h] = None
            t0 = now_ns()
            node.publish(key, bad_value)
            got = node.spin_until(lambda: node.handler_rx[handler] is not None, args.timeout)
            latency = (node.handler_rx[handler] - t0) / 1e3 if got else None
            stop(procs)
            for i, (one, two) in enumerate(pings):
                rows.append(dict(config=args.config, load=args.load, sample=k, probe=probe,
                                 kind="ping", idx=i, one_hop_us=one, two_hop_us=two,
                                 violation_us=None))
            rows.append(dict(config=args.config, load=args.load, sample=k, probe=probe,
                             kind="violation", idx=0, one_hop_us=None, two_hop_us=None,
                             violation_us=latency))
            print(f"{args.config} load={args.load} k={k} {probe}: "
                  f"violation={latency if latency is None else round(latency)}us "
                  f"ping2={[round(p[1]) if p[1] else None for p in pings]}", flush=True)
            node.spin_for(0.3)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["config"])
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
