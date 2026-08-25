#!/usr/bin/env python3
"""Dump live /sst DOAs as paste-ready ODAS static-target config lines.

Place your source(s), run for a few seconds, and copy the printed
`{ tag=..; x=..; y=..; z=..; }` line(s) into the Pi cfg's `sst.target` (with
`sst.add = "static"`) to separate on fixed directions instead of live tracking.

    ros2 run odas_vicon_tools sst_target --duration 3
    ros2 run odas_vicon_tools sst_target --duration 5 --tag-prefix mic

x/y/z are DOA unit vectors, ODAS convention (x forward, y left, z up) — the same
fields the /sst message carries. Each SST id is vector-averaged over the window
and renormalized (cartesian mean avoids the +-180 deg azimuth seam).
"""
import argparse
import math
import sys
import numpy as np
# rclpy / message imports are done inside main() so --self-check runs without ROS.


def vec_to_azimuth(x, y):
    """Azimuth in degrees, ODAS convention (x forward, y left, CCW positive)."""
    return math.degrees(math.atan2(y, x))


def vec_to_elevation(x, y, z):
    """Elevation in degrees above the array plane."""
    r = math.sqrt(x * x + y * y + z * z)
    return math.degrees(math.asin(max(-1.0, min(1.0, z / r)))) if r else 0.0


def average_target(vecs):
    """Vector-mean a list of (x,y,z) DOAs and renormalize to a unit vector."""
    v = np.asarray(vecs, dtype=float).mean(axis=0)
    n = np.linalg.norm(v)
    return v / n if n else v          # n==0 only if all vecs cancel exactly


def format_line(tag, v, n_frames):
    x, y, z = v
    az = vec_to_azimuth(x, y)
    el = vec_to_elevation(x, y, z)
    return (f'{{ tag = "{tag}"; x = {x:+.4f}; y = {y:+.4f}; z = {z:+.4f}; }},'
            f'   # az={az:+.1f}deg  el={el:+.1f}deg  frames={n_frames}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=float, default=3.0, help='seconds to collect')
    parser.add_argument('--tag-prefix', default='src', help='target tag prefix (src1, src2, ...)')
    parser.add_argument('--self-check', action='store_true', help='run the self-test and exit')
    args = parser.parse_args()

    if args.self_check:
        demo()
        return

    import rclpy
    from rclpy.node import Node
    from odas_ros_msgs.msg import OdasSstArrayStamped

    class _Collector(Node):
        def __init__(self, duration):
            super().__init__('sst_target')
            self._duration = duration
            self._start = None
            self._sst = {}          # id -> list of (x, y, z)
            self._order = []        # ids in first-seen order (stable target ordering)
            self._frames = 0
            self.create_subscription(OdasSstArrayStamped, '/sst', self._cb, 10)

        def _cb(self, msg):
            if self._start is None:
                self._start = self.get_clock().now().nanoseconds
            self._frames += 1
            for src in msg.sources:
                if src.id not in self._sst:
                    self._order.append(src.id)
                self._sst.setdefault(src.id, []).append((src.x, src.y, src.z))

        @property
        def done(self):
            return (self._start is not None
                    and (self.get_clock().now().nanoseconds - self._start)
                    >= self._duration * 1e9)

    rclpy.init()
    node = _Collector(args.duration)
    while rclpy.ok() and not node.done:
        rclpy.spin_once(node, timeout_sec=0.1)

    if not node._order:
        print(f"# no active /sst tracks in {args.duration:.1f}s ({node._frames} frames seen)",
              file=sys.stderr)
    else:
        print(f"# {args.duration:.1f}s, {node._frames} /sst frames")
        print("target = (")
        for i, sid in enumerate(node._order, start=1):
            v = average_target(node._sst[sid])
            print("    " + format_line(f"{args.tag_prefix}{i}", v, len(node._sst[sid])))
        print(");")

    node.destroy_node()
    rclpy.shutdown()


def demo():
    """Self-check: averaging is unit-length and recovers the true DOA, incl. the seam."""
    rng = np.random.default_rng(0)

    # Source near +45 deg azimuth, level.
    true1 = np.array([math.cos(math.radians(45)), math.sin(math.radians(45)), 0.0])
    jit1 = [true1 + rng.normal(0, 0.02, 3) for _ in range(40)]
    v1 = average_target(jit1)
    assert abs(np.linalg.norm(v1) - 1.0) < 1e-9, "not unit length"
    assert np.linalg.norm(v1 - true1) < 0.02, "45deg DOA not recovered"

    # Source straddling the +-180 deg seam (x~-1): cartesian mean must not blow up.
    true2 = np.array([-0.999, 0.0447, 0.0])
    true2 = true2 / np.linalg.norm(true2)
    jit2 = [true2 + rng.normal(0, 0.02, 3) for _ in range(40)]
    v2 = average_target(jit2)
    assert abs(np.linalg.norm(v2) - 1.0) < 1e-9, "not unit length"
    assert np.linalg.norm(v2 - true2) < 0.03, "seam DOA not recovered"
    assert abs(vec_to_azimuth(*v2[:2])) > 170, "azimuth should be near +-180deg"

    print("sst_target self-check OK")


if __name__ == '__main__':
    main()
