#!/bin/bash
source /opt/ros/lyrical/setup.bash
EX=/home/eliaslinux/Documents/GitHub/LTLsplitter/tests/monitorExports
OUT=/tmp/claude-1000/-home-eliaslinux-Documents-GitHub/c93bc9e7-1b8d-4e14-8201-d376565433f1/scratchpad/loadtest/nominal
V3="/classifier=0,/state=0,/distance_to_target=10,/alert=false,/halt=false,/slowdown=false,/turnoffUVC=false"
V12="/sRobotClassifier=0,/sRobotState=0,/scan=10,/sRobotAlert=false,/sRobotHalt=false,/sRobotSlowdown=false,/sRobotTurnoffUVC=false"
start() { ( source /tmp/g$1_build_ws/install/setup.bash; exec /tmp/g$1_build_ws/install/copilot/lib/copilot/copilot ) > /dev/null 2>&1 & echo $!; }
for cfg in g1 g2 g12 g3; do
  for n in 2 3 4 6 8; do
    pkill -x copilot; sleep 1
    case $cfg in
      g1) P=$(start 1); A="--package-dir $EX/Group_1 --monitor-pid $P"; V=$V12;;
      g2) P=$(start 2); A="--package-dir $EX/Group_2 --monitor-pid $P"; V=$V12;;
      g12) P=$(start 1); Q=$(start 2); A="--package-dir $EX/Group_1 --package-dir $EX/Group_2 --monitor-pid $P --monitor-pid $Q"; V=$V12;;
      g3) P=$(start 3); A="--package-dir $EX/Group_3 --monitor-pid $P"; V=$V3;;
    esac
    sleep 3
    for i in $(seq 1 $n); do
      python3 $EX/load_test.py $A --values "$V" --rates 2500 --duration 6 --settle 0 --out $OUT/multi_${cfg}_n${n}_t${i}.csv > /dev/null 2>&1 &
    done
    wait $(jobs -p | grep -v "^$P$" | grep -v "^${Q:-x}$") 2>/dev/null
    sleep 1
    python3 - $OUT $cfg $n <<'PY'
import csv, sys
out, cfg, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = [next(csv.DictReader(open(f"{out}/multi_{cfg}_n{n}_t{i}.csv"))) for i in range(1, n + 1)]
rate = sum(float(r["actual_rate_hz"]) for r in rows)
busy = [float(r["monitor_busiest_thread_pct"]) for r in rows]
tot = [float(r["monitor_cpu_pct"]) for r in rows]
ev = sum(int(r["handler_events"]) for r in rows)
print(f"{cfg} testers={n} combined_rate={rate:.0f}Hz monitor_busiest={sum(busy)/n:.1f}% (per-monitor {rows[0]['monitor_busiest_threads']}) total={sum(tot)/n:.0f}% violations={ev}")
PY
  done
done
pkill -x copilot
