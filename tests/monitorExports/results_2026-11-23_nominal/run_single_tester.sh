#!/bin/bash
source /opt/ros/lyrical/setup.bash
REPO=/home/eliaslinux/Documents/GitHub/LTLsplitter
EX=$REPO/tests/monitorExports
OUT=/tmp/claude-1000/-home-eliaslinux-Documents-GitHub/c93bc9e7-1b8d-4e14-8201-d376565433f1/scratchpad/loadtest/nominal
mkdir -p $OUT
V3="/classifier=0,/state=0,/distance_to_target=10,/alert=false,/halt=false,/slowdown=false,/turnoffUVC=false"
V12="/sRobotClassifier=0,/sRobotState=0,/scan=10,/sRobotAlert=false,/sRobotHalt=false,/sRobotSlowdown=false,/sRobotTurnoffUVC=false"
RATES=500,1000,2000,4000,6000,8000,10000
start() { ( source /tmp/g$1_build_ws/install/setup.bash; exec /tmp/g$1_build_ws/install/copilot/lib/copilot/copilot ) > /dev/null 2>&1 & echo $!; }
for rep in 1 2 3; do
  for cfg in g1 g2 g12 g3; do
    pkill -x copilot; sleep 1
    case $cfg in
      g1)  P1=$(start 1); ARGS="--package-dir $EX/Group_1 --monitor-pid $P1"; VALUES=$V12;;
      g2)  P1=$(start 2); ARGS="--package-dir $EX/Group_2 --monitor-pid $P1"; VALUES=$V12;;
      g12) P1=$(start 1); P2=$(start 2); ARGS="--package-dir $EX/Group_1 --package-dir $EX/Group_2 --monitor-pid $P1 --monitor-pid $P2"; VALUES=$V12;;
      g3)  P1=$(start 3); ARGS="--package-dir $EX/Group_3 --monitor-pid $P1"; VALUES=$V3;;
    esac
    sleep 3
    python3 $EX/load_test.py $ARGS --values "$VALUES" --rates $RATES --duration 4 --settle 1 \
      --out $OUT/${cfg}_rep${rep}.csv > $OUT/${cfg}_rep${rep}.log 2>&1
    echo "$cfg rep $rep exit $? | $(grep -E 'violations|fell short' $OUT/${cfg}_rep${rep}.log | tr '\n' ' ')"
    pkill -x copilot; sleep 1
  done
done
