#!/usr/bin/env python3
"""Capture N seconds from SSS source topic(s) and write to WAV.

Single source:
    ros2 run odas_vicon_tools capture_sss --topic /sss/source_1 --duration 5 --output clip.wav

Multiple sources simultaneously:
    ros2 run odas_vicon_tools capture_sss --sources 4 --duration 5 --prefix /tmp/sss
    # writes /tmp/sss_source_0.wav … /tmp/sss_source_3.wav
    ros2 run odas_vicon_tools capture_sss --sources 2 --duration 5 --prefix /tmp/sss
    # writes /tmp/sss_source_0.wav and /tmp/sss_source_1.wav

Alongside the WAV(s) it writes an `*_angles.txt` report with, per active SST track,
the mean azimuth/elevation (ODAS convention: x forward, y left, z up), the azimuth
jitter (stddev), and the SST-id → sss/source_N slot mapping. This verifies which
physical direction each separated slot holds, flags slot drift, and gives the
angular separation between sources (the beamformer-separability ceiling).
"""
import argparse
import math
import wave
import numpy as np
import rclpy
from rclpy.node import Node
from audio_utils_msgs.msg import AudioFrame
from odas_ros_msgs.msg import OdasSstArrayStamped

N_SOURCES = 4


def vec_to_azimuth(x, y):
    """Azimuth in degrees, ODAS convention (x forward, y left, CCW positive)."""
    return math.degrees(math.atan2(y, x))


def vec_to_elevation(x, y, z):
    """Elevation in degrees above the array plane."""
    r = math.sqrt(x * x + y * y + z * z)
    if r == 0:
        return 0.0
    return math.degrees(math.asin(max(-1.0, min(1.0, z / r))))


def _wrap180(deg):
    """Wrap an angle difference into [0, 180]."""
    d = abs(deg) % 360.0
    return 360.0 - d if d > 180.0 else d


class _Capture(Node):
    def __init__(self, duration, topics, mix_topic=None):
        super().__init__('sss_capture')
        self._duration = duration
        self._frames = {t: [] for t in topics}
        self._sr = None
        self._done = {t: False for t in topics}
        for t in topics:
            self.create_subscription(AudioFrame, t, lambda msg, t=t: self._cb(msg, t), 10)

        # Combined mixture: the PRE-SPLIT stream topic (/sss or /sss_pf) is an N-channel
        # interleaved frame, one channel per separated source. Mean-downmixing it gives a
        # mono "unseparated" reference. Captured opportunistically over the same window; it
        # does NOT gate `done`, so a missing topic never hangs the capture.
        self._mix_frames = []
        self._mix_ch = None
        self._mix_sr = None
        if mix_topic:
            self.create_subscription(AudioFrame, mix_topic, self._mix_cb, 10)

        # SST direction tracking (runs on the same capture window).
        self._sst = {}            # id -> list of (x, y, z)
        self._sst_msg_count = 0    # total /sst messages seen (for coverage ratio)
        # /sst preserves slot order (ascending) but the bridge drops the slot index,
        # so we keep the canonical active-id ordering from the fullest frame seen.
        self._sst_order = []       # active ids in slot-ascending order
        self._max_active = 0
        self.create_subscription(OdasSstArrayStamped, '/sst', self._sst_cb, 10)

    def _cb(self, msg, topic):
        if self._done[topic]:
            return
        if self._sr is None:
            self._sr = msg.sampling_frequency
        self._frames[topic].append(bytes(msg.data))
        n_samples = sum(len(f) for f in self._frames[topic]) // 2
        if n_samples >= self._duration * self._sr:
            self._done[topic] = True

    def _sst_cb(self, msg, activity_threshold=0.0):
        # Presence, not loudness: the Pi bridge already drops empty slots (id=0), so any
        # reported track is a live source. Filtering on activity magnitude here caused
        # false "GAPS" for persistent-but-quiet tracks. Keep threshold at 0.0.
        if self.done:
            return
        self._sst_msg_count += 1
        ordered_ids = []
        for src in msg.sources:
            if src.activity >= activity_threshold:
                self._sst.setdefault(src.id, []).append((src.x, src.y, src.z))
                ordered_ids.append(src.id)
        # Keep the ordering from the frame with the most active tracks (stable when
        # all sources are present); that is the canonical slot-ascending order.
        if len(ordered_ids) > self._max_active:
            self._max_active = len(ordered_ids)
            self._sst_order = ordered_ids

    def _mix_cb(self, msg):
        # ponytail: opportunistic — collect until the /sss slots finish; never gates done.
        if self.done:
            return
        if self._mix_ch is None:
            self._mix_ch = msg.channel_count
            self._mix_sr = msg.sampling_frequency
        self._mix_frames.append(bytes(msg.data))

    def save_mix(self, path):
        """Mean-downmix the pre-split N-channel stream to a mono WAV. No-op if it was silent."""
        if not self._mix_frames or not self._mix_ch:
            print("WARNING: no mixture audio captured (topic missing or silent) — skipping mix WAV")
            return
        interleaved = np.frombuffer(b''.join(self._mix_frames), dtype=np.int16)
        interleaved = interleaved[:len(interleaved) // self._mix_ch * self._mix_ch]
        mono = interleaved.reshape(-1, self._mix_ch).mean(axis=1).astype(np.int16)
        mono = mono[:int(self._duration * self._mix_sr)]
        with wave.open(path, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._mix_sr)
            wf.writeframes(mono.tobytes())
        print(f"Saved {len(mono) / self._mix_sr:.2f}s combined mix ({self._mix_ch}ch→mono, "
              f"{self._mix_sr} Hz) → {path}")

    @property
    def done(self):
        return all(self._done.values())

    def _write_wav(self, frames, path, normalize=False):
        raw = b''.join(frames)
        samples = np.frombuffer(raw, dtype=np.int16)[:int(self._duration * self._sr)]
        if normalize:
            peak = np.abs(samples).max()
            if peak > 0:
                samples = (samples.astype(np.float32) * (32767.0 / peak)).astype(np.int16)
        with wave.open(path, 'w') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._sr)
            wf.writeframes(samples.tobytes())
        print(f"Saved {len(samples) / self._sr:.2f}s ({self._sr} Hz) → {path}")

    def save(self, output, normalize=False):
        self._write_wav(list(self._frames.values())[0], output, normalize)

    def save_all(self, prefix, normalize=False):
        for topic, frames in self._frames.items():
            idx = topic.split('_')[-1]
            self._write_wav(frames, f"{prefix}_source_{idx}.wav", normalize)

    def _slot_rms(self):
        """RMS energy per captured slot: {slot_index: rms}. Silent slots ~ noise floor."""
        rms = {}
        for topic, frames in self._frames.items():
            slot = int(topic.split('_')[-1])
            s = np.frombuffer(b''.join(frames), dtype=np.int16).astype(np.float64)
            rms[slot] = float(np.sqrt(np.mean(s * s))) if s.size else 0.0
        return rms

    def _id_azimuth(self, sid):
        """(mean_az, std_az, mean_el, frames) for one SST id."""
        vecs = self._sst[sid]
        az = np.array([vec_to_azimuth(x, y) for x, y, _ in vecs])
        el = np.array([vec_to_elevation(x, y, z) for x, y, z in vecs])
        # ponytail: plain stddev; wrong near the ±180° seam, fine for sources off it.
        return float(np.mean(az)), float(np.std(az)), float(np.mean(el)), len(vecs)

    def angles_report(self, expected=None):
        """SST azimuth + SST↔SSS slot mapping (by energy ordering) + drift report."""
        total = self._sst_msg_count
        ordered_ids = self._sst_order
        if not ordered_ids:
            return ("No active SST tracks during capture "
                    f"(activity < threshold or /sst silent; {total} /sst msgs seen).\n")

        # Map tracks to SSS slots WITHOUT relying on id: /sst active tracks come in
        # slot-ascending order; the K loudest captured slots (K = #active tracks) are
        # the active ones, also taken ascending. Zip them positionally.
        k = len(ordered_ids)
        rms = self._slot_rms()
        active_slots = sorted(sorted(rms, key=lambda s: rms[s], reverse=True)[:k])
        slot_to_id = dict(zip(active_slots, ordered_ids))

        lines = []
        az_by_slot = {}
        for slot in active_slots:
            sid = slot_to_id[slot]
            mean_az, std_az, mean_el, n = self._id_azimuth(sid)
            az_by_slot[slot] = mean_az
            coverage = n / total if total else 0.0
            gap = "" if coverage >= 0.8 else f"  GAPS(coverage={coverage:.0%})"
            lines.append(
                f"source_{slot} <- id {sid}: az = {mean_az:+.1f}° ± {std_az:.1f}°"
                f"   el = {mean_el:+.1f}°   rms={rms[slot]:.0f}   frames={n}{gap}")

        silent = sorted(s for s in rms if s not in active_slots)
        if silent:
            lines.append("silent slots: " + ", ".join(
                f"source_{s}(rms={rms[s]:.0f})" for s in silent))

        # Pairwise azimuth separation = beamformer separability ceiling.
        for i in range(len(active_slots)):
            for j in range(i + 1, len(active_slots)):
                a, b = active_slots[i], active_slots[j]
                sep = _wrap180(az_by_slot[a] - az_by_slot[b])
                verdict = ">20° separable" if sep > 20 else "<20° GEOMETRY CEILING"
                lines.append(f"separation source_{a} vs source_{b}: "
                             f"{sep:.1f}°  ({verdict})")

        # Drift: more distinct tracks than we asked for = a slot changed source.
        seen = len(self._sst)
        if expected is not None and seen > expected:
            lines.append(f"DRIFT: {seen} distinct SST ids seen but only "
                         f"{expected} source(s) expected — a slot may have switched sources.")

        return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sources', type=int, default=None, metavar='N',
                        help='capture N sources simultaneously (source_0 … source_N-1)')
    parser.add_argument('--prefix', default='/tmp/sss', help='output prefix for multi-source mode')
    parser.add_argument('--topic', default='/sss/source_0', help='topic for single-source mode')
    parser.add_argument('--duration', type=float, default=5.0, help='seconds to capture')
    parser.add_argument('--output', default='sss_capture.wav', help='output path for single-source mode')
    parser.add_argument('--normalize', action='store_true', help='normalize each WAV to full scale before saving')
    parser.add_argument('--stream', default='sss',
                        help="source stream in --sources mode: 'sss' (separated) or 'sss_pf' (postfiltered)")
    parser.add_argument('--mix', action='store_true',
                        help='also capture the pre-split /<stream> topic, mean-downmixed to <prefix>_mix.wav '
                             '(combined "unseparated" reference)')
    args = parser.parse_args()

    if args.sources is not None:
        if not 1 <= args.sources <= N_SOURCES:
            raise SystemExit(f"--sources must be between 1 and {N_SOURCES}")
        # SST ids are assigned dynamically (1..4), so N real sources may land on ANY
        # slots (e.g. ids 1 and 4 -> source_0 and source_3). Always capture all slots;
        # --sources is only the expected count for the drift check. The angles report
        # tells you which slots are actually live.
        topics = [f'/{args.stream}/source_{i}' for i in range(N_SOURCES)]
        print(f"Capturing {args.duration}s from all {N_SOURCES} /{args.stream} slots "
              f"(expecting {args.sources} active source(s)) ...")
    else:
        topics = [args.topic]
        print(f"Capturing {args.duration}s from {args.topic} ...")

    # The pre-split stream topic feeds the mixture downmix: /sss (or /sss_pf under --pf).
    mix_topic = f'/{args.stream}' if args.mix else None

    rclpy.init()
    node = _Capture(args.duration, topics, mix_topic=mix_topic)
    while rclpy.ok() and not node.done:
        rclpy.spin_once(node, timeout_sec=0.1)

    if args.sources is not None:
        node.save_all(args.prefix, normalize=args.normalize)
        report_path = f"{args.prefix}_angles.txt"
        mix_path = f"{args.prefix}_mix.wav"
    else:
        node.save(args.output, normalize=args.normalize)
        report_path = args.output.rsplit('.', 1)[0] + "_angles.txt"
        mix_path = args.output.rsplit('.', 1)[0] + "_mix.wav"

    if args.mix:
        node.save_mix(mix_path)

    report = node.angles_report(expected=args.sources)
    print("\n--- SST angles ---\n" + report)
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"Angles → {report_path}")

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
