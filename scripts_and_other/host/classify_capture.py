#!/usr/bin/env python3
"""Classify the ACTIVE separated slots of a capture with CLAP: fine label -> coarse.

Reads the capture's `_angles.txt` to know which slots hold real sources (so silent
slots are skipped), peak-normalizes each slot (SSS output is very low level — CLAP
needs full-scale input), runs zero-shot on general_fine labels, and maps the result
to a coarse category.

    python classify_capture.py 2026-07-28-09-48
    python classify_capture.py captures/2026-07-28-09-48_sss-source-0.wav   # single file

Results are also written to `<prefix>_clap.txt` (or next to a single wav). Override with
--out, and swap label sets with --labels/--mapping to compare vocabularies on the same
audio.

Works on any WAVs, so once the postfiltered stream is bridged you can classify a
`/sss` capture and a `/sss_pf` capture and compare bleed directly.
"""
import os
import re
import csv
import glob
import argparse

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402
from clap_utils import load_audio_file  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# CLAP model: place it under host/models/laion-clap-htsat-unfused, or set CLAP_MODEL.
MODEL = os.environ.get("CLAP_MODEL", os.path.join(HERE, "models/laion-clap-htsat-unfused"))
FINE = os.path.join(HERE, "labels/general_fine.txt")
FINE_TO_COARSE = os.path.join(HERE, "candidate_mapping/general_fine_to_coarse.csv")
CAPTURES = os.path.join(HERE, "captures")
TOPK = 5


def load_labels_and_map(fine=FINE, fine_to_coarse=FINE_TO_COARSE):
    labels = [l.strip() for l in open(fine) if l.strip()]
    coarse = {}
    with open(fine_to_coarse) as f:
        for row in csv.DictReader(f):
            coarse[row["fine_label"].strip()] = row["coarse_label"].strip()
    return labels, coarse


def default_out(arg):
    """Where to save results: <prefix>_clap.txt, or alongside a single wav."""
    if arg.endswith(".wav"):
        return arg[:-4] + "_clap.txt"
    prefix = arg if os.path.isabs(arg) or arg.startswith("captures/") \
        else os.path.join(CAPTURES, arg)
    return (prefix[:-1] if prefix.endswith("_") else prefix) + "_clap.txt"


def resolve_wavs(arg):
    """Return [(label, wav_path)] for a timestamp, prefix, or single wav."""
    if arg.endswith(".wav"):
        return [(os.path.basename(arg), arg)]
    prefix = arg if os.path.isabs(arg) or arg.startswith("captures/") \
        else os.path.join(CAPTURES, arg)
    prefix = prefix[:-1] if prefix.endswith("_") else prefix

    # The combined mixture (if captured with --mix) goes first, as the baseline to compare
    # every separated slot against.
    mix = f"{prefix}_mix.wav"
    lead = [("MIX (combined)", mix)] if os.path.exists(mix) else []

    angles = f"{prefix}_angles.txt"
    active = []
    if os.path.exists(angles):
        for line in open(angles):
            m = re.match(r"source_(\d+)\s*<-\s*id\s*(\d+)", line)
            if m:
                active.append((int(m.group(1)), line.strip()))
    if active:
        return lead + [(ctx, f"{prefix}_sss-source-{slot}.wav") for slot, ctx in active]
    # No angles report -> fall back to every slot present.
    print(f"(no active-slot info in {angles}; classifying all slots found)")
    return lead + [(os.path.basename(p), p)
                   for p in sorted(glob.glob(f"{prefix}_sss-source-*.wav"))]


def coarse_ranking(fine_scores, coarse_map):
    """Sum fine scores into their coarse buckets."""
    agg = {}
    for lab, sc in fine_scores.items():
        agg[coarse_map.get(lab, "?")] = agg.get(coarse_map.get(lab, "?"), 0.0) + sc
    return sorted(agg.items(), key=lambda kv: kv[1], reverse=True)


def main():
    p = argparse.ArgumentParser(description="CLAP fine->coarse classification of a capture.")
    p.add_argument("target", help="capture timestamp/prefix, or a single .wav")
    p.add_argument("--out", help="results file (default <prefix>_clap.txt; '-' to skip saving)")
    p.add_argument("--labels", default=FINE, help="fine-label file (default general_fine.txt)")
    p.add_argument("--mapping", default=FINE_TO_COARSE, help="fine->coarse csv")
    args = p.parse_args()

    labels, coarse_map = load_labels_and_map(args.labels, args.mapping)
    wavs = resolve_wavs(args.target)
    if not wavs:
        raise SystemExit("No WAVs found for that argument.")

    from transformers import pipeline
    clf = pipeline("zero-shot-audio-classification", model=MODEL, local_files_only=True)
    sr = clf.feature_extractor.sampling_rate

    lines = [f"# CLAP unfused: {args.target}",
             f"# labels={os.path.basename(args.labels)}  ({len(labels)} fine labels)"]
    for ctx, wav in wavs:
        if not os.path.exists(wav):
            lines.append(f"\n=== {ctx} ===\n  MISSING: {wav}")
            continue
        a = load_audio_file(wav, sr)
        peak = float(np.abs(a).max())
        if peak > 0:
            a = a / peak                 # peak-normalize: SSS output is near-silent
        res = clf(a, candidate_labels=labels)
        fine_scores = {r["label"]: r["score"] for r in res}
        lines.append(f"\n=== {ctx} ===   (orig peak {peak:.4f} of full scale)")
        for r in res[:TOPK]:
            lines.append(f"  fine  {r['score']:.3f}  {r['label']:<22} -> {coarse_map.get(r['label'], '?')}")
        top_coarse = coarse_ranking(fine_scores, coarse_map)[:3]
        lines.append("  coarse: " + ", ".join(f"{c} {s:.2f}" for c, s in top_coarse))

    out_text = "\n".join(lines)
    print(out_text)

    out = args.out or default_out(args.target)
    if out != "-":
        with open(out, "w") as f:
            f.write(out_text + "\n")
        print(f"\nresults → {out}")


if __name__ == "__main__":
    main()
