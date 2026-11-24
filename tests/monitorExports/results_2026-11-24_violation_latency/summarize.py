"""Summarize violation-latency results: per config x load x probe, median / p95 / max (us)."""
import csv
import glob
import statistics as st
import sys
from collections import defaultdict

res = sys.argv[1]
viol = defaultdict(list)
lost = defaultdict(int)
one = defaultdict(list)
two = defaultdict(list)
for path in sorted(glob.glob(f"{res}/g*_n*.csv")):
    for r in csv.DictReader(open(path)):
        key = (r["config"], int(r["load"]))
        if r["kind"] == "violation":
            if r["violation_us"]:
                viol[key + (r["probe"],)].append(float(r["violation_us"]))
                viol[key + ("all",)].append(float(r["violation_us"]))
            else:
                lost[key + (r["probe"],)] += 1
                lost[key + ("all",)] += 1
        elif int(r["idx"]) > 0:  # first ping per sample is a first-message warm-up
            if r["one_hop_us"]:
                one[key].append(float(r["one_hop_us"]))
            if r["two_hop_us"]:
                two[key].append(float(r["two_hop_us"]))


def q(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    i = min(len(xs) - 1, max(0, round(p / 100 * (len(xs) - 1))))
    return xs[i]


print("config,load,probe,n,lost,median,p95,max,ping1_median,ping2_median,ping2_p95")
for key in sorted(viol.keys() | lost.keys(), key=lambda k: (k[0], k[1], k[2])):
    xs = viol.get(key, [])
    base = key[:2]
    print(f"{key[0]},{key[1]},{key[2]},{len(xs)},{lost.get(key, 0)},"
          f"{q(xs, 50):.0f},{q(xs, 95):.0f},{max(xs) if xs else float('nan'):.0f},"
          f"{q(one[base], 50):.0f},{q(two[base], 50):.0f},{q(two[base], 95):.0f}")
