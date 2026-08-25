#!/usr/bin/env python3
"""Monitor /sst for N seconds and log each track's activity over time.

Diagnostic for SST persistence: shows whether a tracked source stays alive and how
its `activity` value evolves (RViz shows an arrow whenever a track exists, even when
its activity is low — this reveals what the number actually does through the window).

    ros2 run odas_vicon_tools sst_monitor --duration 10
    ros2 run odas_vicon_tools sst_monitor --duration 10 --csv /tmp/sst_log.csv

Prints a per-id summary + an ASCII activity timeline, and optionally a CSV
(t_sec, id, activity, azimuth_deg) for plotting.
"""
import argparse
import math
import time

import rclpy
from rclpy.node import Node
from odas_ros_msgs.msg import OdasSstArrayStamped

COLS = 60  # timeline width in characters


def _az(x, y):
    return math.degrees(math.atan2(y, x))


class _Monitor(Node):
    def __init__(self):
        super().__init__('sst_monitor')
        self.rows = []      # (t, id, activity, az)
        self.n_msgs = 0
        self.t0 = None
        self.create_subscription(OdasSstArrayStamped, '/sst', self._cb, 50)

    def _cb(self, msg):
        now = time.monotonic()
        if self.t0 is None:
            self.t0 = now
        self.n_msgs += 1
        t = now - self.t0
        for s in msg.sources:            # no activity filter — log everything
            self.rows.append((t, s.id, s.activity, _az(s.x, s.y)))


def _timeline(rows, duration, sid):
    """One ASCII row: activity per time-bucket for a given id."""
    buckets = [None] * COLS
    for t, rid, act, _ in rows:
        if rid != sid:
            continue
        c = min(COLS - 1, int(t / duration * COLS))
        buckets[c] = act if buckets[c] is None else max(buckets[c], act)
    out = []
    for b in buckets:
        if b is None:
            out.append(' ')          # track absent this bucket
        elif b < 0.3:
            out.append('.')          # present but low activity
        elif b < 0.6:
            out.append(':')
        else:
            out.append('#')          # strong activity
    return ''.join(out)


def report(mon, duration):
    lines = []
    rate = mon.n_msgs / duration if duration else 0.0
    lines.append(f"/sst monitor: {duration:.1f}s, {mon.n_msgs} msgs ({rate:.0f} Hz)")
    if not mon.rows:
        lines.append("No /sst messages received — is the pipeline publishing?")
        return "\n".join(lines) + "\n"

    ids = sorted({r[1] for r in mon.rows})
    lines.append(f"{'id':>4}  {'msgs':>5}  {'cov':>4}  "
                 f"{'act min/mean/max':>18}  {'az°':>7}")
    for sid in ids:
        acts = [r[2] for r in mon.rows if r[1] == sid]
        azs = [r[3] for r in mon.rows if r[1] == sid]
        n = len(acts)
        cov = n / mon.n_msgs if mon.n_msgs else 0.0
        amin, amax = min(acts), max(acts)
        amean = sum(acts) / n
        lines.append(f"{sid:>4}  {n:>5}  {cov:>3.0%}  "
                     f"{amin:>5.2f}/{amean:.2f}/{amax:.2f}  {sum(azs)/n:>+7.1f}")

    lines.append("")
    lines.append(f"timeline (each col ~{duration/COLS:.2f}s):  "
                 "' '=absent  .=<0.3  :=0.3-0.6  #=>0.6")
    for sid in ids:
        lines.append(f"{sid:>4} |{_timeline(mon.rows, duration, sid)}|")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=10.0, help='seconds to monitor')
    parser.add_argument('--csv', default=None, help='optional CSV path for raw samples')
    args = parser.parse_args()

    rclpy.init()
    mon = _Monitor()
    print(f"Monitoring /sst for {args.duration}s ...")
    start = time.monotonic()
    while rclpy.ok() and (time.monotonic() - start) < args.duration:
        rclpy.spin_once(mon, timeout_sec=0.1)

    print("\n" + report(mon, args.duration))

    if args.csv:
        import csv
        with open(args.csv, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['t_sec', 'id', 'activity', 'azimuth_deg'])
            w.writerows(mon.rows)
        print(f"Raw samples → {args.csv}")

    mon.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
