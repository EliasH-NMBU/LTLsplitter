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

**Validated against both real compiled monitors, not just reasoned through.** ROS 2 Lyrical Luth
and the Haskell `copilot` package were installed in the LTLsplitter dev sandbox, both groups'
real `copilot` nodes were built with `colcon build --packages-select copilot` (the sibling
`test_requirements` package fails to build on this ROS2 release over an unrelated deprecated
CMake macro, `ament_target_dependencies` -- build `copilot` alone), and `load_test.py` was run
against each at rates from 100 to 5000 Hz. Both showed the real saturation signature this script
looks for -- handler-event throughput peaking then declining as the publish rate kept climbing
-- with Group_2 (9 requirements) sustaining meaningfully higher throughput before saturating
than Group_1 (13 requirements). One real bug this process caught, now fixed: `LoadTestNode`
originally named its own tracking dicts `self._publishers`/`self._subscriptions`, which silently
collide with rclpy's own `Node` internals of the same name and crashed `destroy_node()`.
`parse_monitor_interface` (the part that doesn't need ROS2 at all) is additionally covered by
`tests/test_load_test.py` in the main test suite, run directly against the real `Group_1`/
`Group_2` files here.

One gotcha worth knowing if you regenerate the C code yourself: `runhaskell Copilot.hs` writes
`copilot.c`/`copilot.h`/`copilot_types.h` to the **current directory**, not next to the `.hs`
file -- run it from inside `copilot/src/`, or the generated files land one directory too high
for the C++ build to find them.
