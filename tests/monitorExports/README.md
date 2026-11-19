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

**This was written and reasoned through carefully, but never run end to end** -- the LTLsplitter
dev sandbox it was written in has no ROS2 install at all. `parse_monitor_interface` (the one
part that doesn't need ROS2) *was* verified directly against the real `Group_1`/`Group_2` files
here -- see `tests/test_load_test.py` in the main test suite. The `rclpy`-dependent parts
(`LoadTestNode`, `run_rate_step`, `main`) follow the standard documented API but weren't
exercised; sanity-check the first rate step's output in your real environment (the same
Docker/screen session as the "Copilot RV" pane -- see `Group_1/screenrc`) before trusting a full
run.
