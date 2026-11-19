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
The script infers overload instead from two external symptoms: handler-event throughput failing
to keep scaling with the publish rate, and handler events arriving in bursty, uneven gaps. Both
are reported per rate step (and in the CSV) rather than collapsed into a single pass/fail.

**Validated against a real rclpy node, not just reasoned through** -- ROS 2 Lyrical Luth was
installed in the LTLsplitter dev sandbox afterwards (it has Tier 1 support for this machine's
Ubuntu 26.04), and this was run end to end against a throwaway stand-in node at several rates,
including a zero-handler-events case: publish counts matched the target rate exactly every time,
and it shut down and wrote its CSV cleanly. That run caught one real bug, now fixed:
`LoadTestNode` originally named its own tracking dicts `self._publishers`/`self._subscriptions`,
which silently collide with rclpy's own `Node` internals of the same name and crashed
`destroy_node()`. `parse_monitor_interface` (the part that doesn't need ROS2 at all) was
additionally verified directly against the real `Group_1`/`Group_2` files here -- see
`tests/test_load_test.py` in the main test suite.

It has **not** been run against the real compiled `copilot` monitor -- that needs the
Haskell/colcon toolchain the Docker image builds with, which isn't set up in this sandbox.
Sanity-check the first rate step's output against a real monitor (the same Docker/screen session
as the "Copilot RV" pane -- see `Group_1/screenrc`) before trusting a full run there.
