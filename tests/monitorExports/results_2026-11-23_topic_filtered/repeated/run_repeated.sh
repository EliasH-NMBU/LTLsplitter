#!/bin/bash
source /opt/ros/lyrical/setup.bash
EX=/home/eliaslinux/Documents/GitHub/LTLsplitter/tests/monitorExports
OUT=/tmp/claude-1000/-home-eliaslinux-Documents-GitHub/c93bc9e7-1b8d-4e14-8201-d376565433f1/scratchpad/loadtest/repeated/rep$1
mkdir -p $OUT
V3="/classifier=0,/state=0,/distance_to_target=10,/alert=false,/halt=false,/slowdown=false,/turnoffUVC=false"
V12="/sRobotClassifier=0,/sRobotState=0,/scan=10,/sRobotAlert=false,/sRobotHalt=false,/sRobotSlowdown=false,/sRobotTurnoffUVC=false"
start() { ( source /tmp/$1_build_ws/install/setup.bash; exec /tmp/$1_build_ws/install/copilot/lib/copilot/copilot ) > /dev/null 2>&1 & echo $!; }
for cfg in g1s g2s g1s2s g12 g3; do
  for n in 1 4 6 7 8 10 12 14; do
    pkill -x copilot; sleep 1; Q=
    case $cfg in
      g1s)   P=$(start g1s); A="--package-dir /tmp/g1s_build_ws/src --monitor-pid $P"; V=$V12;;
      g2s)   P=$(start g2s); A="--package-dir /tmp/g2s_build_ws/src --monitor-pid $P"; V=$V12;;
      g1s2s) P=$(start g1s); Q=$(start g2s); A="--package-dir /tmp/g1s_build_ws/src --package-dir /tmp/g2s_build_ws/src --monitor-pid $P --monitor-pid $Q"; V=$V12;;
      g12)   P=$(start g1); Q=$(start g2); A="--package-dir $EX/Group_1 --package-dir $EX/Group_2 --monitor-pid $P --monitor-pid $Q"; V=$V12;;
      g3)    P=$(start g3); A="--package-dir $EX/Group_3 --monitor-pid $P"; V=$V3;;
    esac
    sleep 3
    PIDS=()
    for i in $(seq 1 $n); do
      python3 $EX/load_test.py $A --values "$V" --rates 2500 --duration 6 --settle 0 --out $OUT/${cfg}_n${n}_t${i}.csv > $OUT/${cfg}_n${n}_t${i}.log 2>&1 &
      PIDS+=($!)
    done
    wait "${PIDS[@]}"
    python3 - $OUT $cfg $n <<'PY'
import csv, sys
out, cfg, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = [next(csv.DictReader(open(f"{out}/{cfg}_n{n}_t{i}.csv"))) for i in range(1, n + 1)]
rate = sum(float(r["actual_rate_hz"]) for r in rows)
per = [[float(x) for x in r["monitor_busiest_threads"].split()] for r in rows]
avg = [sum(c) / n for c in zip(*per)]
tot = sum(float(r["monitor_cpu_pct"]) for r in rows) / n
ev = sum(int(r["handler_events"]) for r in rows)
print(f"{out.rsplit('rep', 1)[1]},{cfg},{n},{rate:.0f},{' / '.join(f'{a:.1f}' for a in avg)},{tot:.0f},{ev}")
PY
  done
done
pkill -x copilot
