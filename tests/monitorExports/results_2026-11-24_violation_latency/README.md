# Violation response time under nominal background load (2026-11-24)

How long a monitor takes to report a violation while it is also processing a nominal
background load, compared with a plain ROS 2 round trip under the same load.

## Method

- **Background load**: 0–8 parallel `load_test.py` testers at 2,500 rounds/s each, publishing the
  same fixed nominal values as the earlier load tests (0–20,000 rounds/s target).
- **Probe** (`violation_probe.py`, rclpy): per sample it restarts the monitor(s), waits for
  discovery plus 3 s under load, then publishes ONE violating value and records the time until
  the first message on that requirement's handler topic. Every requirement is
  `PTLTL.alwaysBeen`, so a violation latches and only the first handler message is clean, which
  is why the monitors are restarted (SIGINT) before every sample.
  - `halt` probe: `halt=true` while `state=0` violates `operationalstate_0_2` (in Group 1).
  - `class` probe: `classifier=1` at distance 10 violates `state_req101` (in Group 2).
  - Samples alternate between the two probes: 40 per cell, 20 per probe.
- **ROS 2 baseline**: in the same sample, before the violation, the probe pings a C++ relay
  (`probe_relay/`): it receives a `std_msgs/Bool` and publishes `std_msgs/Empty`, the same
  depth-10 receive-then-publish path as a generated monitor but with no evaluation and no
  background topics. `ping2` = probe -> relay -> probe (two hops, same shape as
  probe -> monitor -> probe); `ping1` = probe -> its own subscription (one hop). The first ping
  of each sample is dropped as a first-message warm-up.
- **Transport**: all processes use `FASTDDS_BUILTIN_TRANSPORTS=UDPv4`. A first attempt over the
  default shared-memory transport, with monitors SIGKILLed between samples, left stale Fast DDS
  shared-memory ports behind and lost deliveries under load; those results were discarded.
- **Achieved load**: the testers were stopped mid-step, so `achieved_load_check/` holds a
  separate 6 s check at the high-load levels under the same UDP setup.

## Files

- `raw/<config>_n<testers>.csv|log`: per-sample results (`config`: `g3`, `g12` = Group 1 + 2
  all topics, `g1s2s` = Group 1 + 2 own topics).
- `summary.csv`: per config x load x probe: samples, lost, median / p95 / max response (us), and
  the ROS 2 ping medians/p95 (us). Rebuild with `python3 summarize.py raw > summary.csv`.
- `run_latency.sh`: the sweep (`run_latency.sh OUTDIR SAMPLES`).
