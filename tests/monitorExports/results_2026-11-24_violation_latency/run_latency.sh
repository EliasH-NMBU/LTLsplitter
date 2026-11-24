#!/bin/bash
# Violation response time vs background nominal load, per monitor configuration.
# Usage: run_latency.sh OUTDIR SAMPLES "CONFIGS" "TESTER_COUNTS"
source /opt/ros/lyrical/setup.bash
S=/tmp/claude-1000/-home-eliaslinux-Documents-GitHub/c93bc9e7-1b8d-4e14-8201-d376565433f1/scratchpad/latency
EX=/home/eliaslinux/Documents/GitHub/LTLsplitter/tests/monitorExports
OUT=$1; SAMPLES=$2; CONFIGS=${3:-"g3 g12 g1s2s"}; COUNTS=${4:-"0 1 4 6 7 8"}
mkdir -p $OUT
source $S/relay_ws/install/setup.bash
# UDP loopback for every process in this experiment: monitors are restarted every sample, and
# Fast DDS shared-memory ports left by stopped participants made deliveries fail under load.
export FASTDDS_BUILTIN_TRANSPORTS=UDPv4
V3="/classifier=0,/state=0,/distance_to_target=10,/alert=false,/halt=false,/slowdown=false,/turnoffUVC=false"
V12="/sRobotClassifier=0,/sRobotState=0,/scan=10,/sRobotAlert=false,/sRobotHalt=false,/sRobotSlowdown=false,/sRobotTurnoffUVC=false"
stop_pids() {  # SIGINT, then SIGKILL whatever is still alive after 5 s
  [ $# -eq 0 ] && return
  kill -INT "$@" 2>/dev/null
  for _ in $(seq 1 50); do kill -0 "$@" 2>/dev/null || break; sleep 0.1; done
  kill -9 "$@" 2>/dev/null
}
sleep 100000 & DUMMY=$!   # stable pid for the testers' CPU sampler (monitors restart every sample)
for cfg in $CONFIGS; do
  case $cfg in
    g3)    A="--package-dir $EX/Group_3"; V=$V3;;
    g12)   A="--package-dir $EX/Group_1 --package-dir $EX/Group_2"; V=$V12;;
    g1s2s) A="--package-dir /tmp/g1s_build_ws/src --package-dir /tmp/g2s_build_ws/src"; V=$V12;;
  esac
  for n in $COUNTS; do
    [ -s $OUT/${cfg}_n${n}.csv ] && continue
    $S/relay_ws/install/probe_relay/lib/probe_relay/relay > /dev/null 2>&1 &
    RELAY=$!
    PIDS=()
    for i in $(seq 1 $n); do
      python3 $EX/load_test.py $A --monitor-pid $DUMMY --values "$V" --rates 2500 --duration 400 --settle 0 \
        --out $OUT/bg_${cfg}_n${n}_t${i}.csv > $OUT/bg_${cfg}_n${n}_t${i}.log 2>&1 &
      PIDS+=($!)
    done
    sleep 3
    python3 $S/violation_probe.py --config $cfg --load $((n * 2500)) --samples $SAMPLES --warmup 3 \
      --out $OUT/${cfg}_n${n}.csv > $OUT/${cfg}_n${n}.log 2>&1
    stop_pids "${PIDS[@]}" $RELAY
    pkill -INT -x copilot; sleep 1; pkill -9 -x copilot
    fastdds shm clean > /dev/null 2>&1
    echo "done $cfg n=$n"
  done
done
kill $DUMMY
