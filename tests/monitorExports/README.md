# monitorExports

This directory holds real monitor packages produced by LTLsplitter's page 4 "Generate Monitor"
(e.g. `Group_1/`, `Group_2/`) -- regeneratable build output from a real run, not something this
repo's own test suite depends on.

## load_test.py

Load-tests one of those generated packages: publishes synthetic input data at steadily ramping
rates and watches how its violation ("handler") topics respond, to find the rate at which it
starts falling behind rather than just whether it eventually produces a verdict.

```
python3 load_test.py --package-dir Group_1 --rates 10,20,50,100,200,500,1000,2000 \
    --duration 5 --out group1_results.csv
```

Run once per group -- it tests one monitor at a time by design, so a result is never a mix of
two monitors' saturation points. Topic names and types are discovered directly from that
group's own `copilot/src/copilot_monitor.cpp` (not hand-entered), so it stays correct for
whatever requirements a group actually ended up with.

**Read the methodology note at the top of the script before trusting its numbers** -- in short:
the generated monitor's subscriptions use ROS2's default QoS (depth 10, oldest-dropped), and the
message types carry no sequence number, so there's no way to directly count drops from outside.
The script infers overload instead from one external symptom: handler-event throughput failing
to keep scaling with the publish rate (or dropping outright) as the publish rate keeps climbing.
Each handler event is counted with a plain per-topic integer increment, not a timestamp log --
an earlier version recorded a `time.monotonic()` timestamp per event to also compute inter-
arrival burstiness, dropped because that second signal was never used by the automated check
anyway, and per-event timestamping is overhead in *this script's own* subscriber callbacks, not
the monitor being measured -- if those callbacks fell behind their own incoming queue (same
default QoS as everything else here), that would misattribute this script's own bottleneck to
the monitor's.

The report also includes `requirement_checks_per_sec` -- the real load on the monitor, not just
the raw publish rate: `copilot_monitor.cpp` calls `step()` once per message received (every
input topic's callback independently calls it), and each `step()` re-evaluates every registered
requirement at once, so the real check rate is `round_rate * num_input_topics * num_requirements`,
not the round rate alone.

**Correction (2026-11-23): handler-event throughput alone measured this script, not the
monitors.** Sampling per-thread CPU from `/proc` showed this script's own Python executor thread
at ~100% already at 100 Hz for the 13- and 22-requirement groups, while the monitor itself was
far from busy -- so the earlier "both groups peak around 500 Hz" reading of the handler-event
rate was this script's counting ceiling. Each step now also records the monitor's CPU (total and
busiest thread, i.e. its executor thread, which is what saturates), its CPU time per `step()`
call, and a `tester_saturated` flag; when that flag is true, read the monitor columns, not the
handler-event ones. The monitor is found by process name (`copilot`) or `--monitor-pid`.

Results for Group_1 (13 requirements), Group_2 (9) and Group_3 (all 22 in one monitor), 3
repetitions each, rates 50-3000 Hz, are in `results_2026-11-23/`. Estimated capacity (rate at
which the monitor's executor thread reaches 100%, extrapolated from steps below 85%):
Group_1 ~580 Hz, Group_2 ~1420 Hz, Group_3 ~420 Hz; CPU per step() below saturation ~370 us,
~160 us and ~500 us. Above saturation the per-step figure falls only because messages are being
dropped (the denominator counts published, not processed, messages) -- don't read it there.

Built with ROS 2 Lyrical Luth and the Haskell `copilot` package: `colcon build
--packages-select copilot` (the sibling `test_requirements` package fails to build on this ROS2
release over the deprecated `ament_target_dependencies` macro -- build `copilot` alone). One bug
an earlier run caught: `LoadTestNode` originally named its tracking dicts `self._publishers`/
`self._subscriptions`, which collide with rclpy's own `Node` internals and crashed
`destroy_node()`. `parse_monitor_interface` (no ROS2 needed) is covered by
`tests/test_load_test.py`.

One gotcha worth knowing if you regenerate the C code yourself: `runhaskell Copilot.hs` writes
`copilot.c`/`copilot.h`/`copilot_types.h` to the **current directory**, not next to the `.hs`
file -- run it from inside `copilot/src/`, or the generated files land one directory too high
for the C++ build to find them.
