#!/usr/bin/env python3
"""
Cosine similarity between two sounds via CLAP unfused audio embeddings.

CLAP audio embeddings are L2-normalized, so cosine similarity == dot product.

    python sound_similarity.py a.wav b.wav [more.wav ...]
    python sound_similarity.py --heatmap out.png a.wav b.wav [more.wav ...]

Two files -> prints their cosine similarity.
3+ files -> prints the full pairwise similarity matrix.
--heatmap out.png -> also saves the matrix as an annotated heatmap image.

---
How to run

# two sounds -> one number
sound_similarity.py a.wav b.wav

# many sounds -> pairwise matrix
sound_similarity.py a.wav b.wav c.wav

"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402

from clap_utils import load_audio_file  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
# CLAP model: place it under host/models/laion-clap-htsat-unfused, or set CLAP_MODEL.
MODEL = os.environ.get("CLAP_MODEL", os.path.join(HERE, "models/laion-clap-htsat-unfused"))


def embed(paths):
    from transformers import pipeline
    clf = pipeline("zero-shot-audio-classification", model=MODEL, local_files_only=True)
    model, fe = clf.model, clf.feature_extractor
    model.eval()
    sr = int(fe.sampling_rate)
    audio = [load_audio_file(p, target_sr=sr) for p in paths]
    import torch
    with torch.no_grad():
        inp = fe(audio, sampling_rate=sr, return_tensors="pt")
        return model.get_audio_features(**inp).cpu().numpy().astype(np.float32)  # [N,512] unit-norm


def selftest():
    # cosine of unit vectors == dot product; identical->1, orthogonal->0
    a = np.array([[1, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32)
    m = a @ a.T
    assert np.isclose(m[0, 1], 1.0) and np.isclose(m[0, 2], 0.0)
    print("selftest OK")


def short_labels(names):
    """Drop the shared capture prefix + .wav, and compact slot names → mix / src0 / pf1."""
    base = [n[:-4] if n.endswith(".wav") else n for n in names]
    pre = os.path.commonprefix(base)
    cut = max(pre.rfind("_"), pre.rfind("-")) + 1   # only strip whole tokens, not mid-word
    pre = pre[:cut]
    out = []
    for b in base:
        s = (b[len(pre):] or b).lstrip("_-")
        s = s.replace("sss_pf-source-", "pf").replace("sss-source-", "src")
        out.append(s)
    return out


def save_heatmap(sim, names, out_path):
    """Render an N x N cosine matrix as an annotated heatmap (short, descriptive labels)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = short_labels(names)
    n = len(labels)
    fig, ax = plt.subplots(figsize=(max(4, n * 0.9), max(3.5, n * 0.9)))
    im = ax.imshow(sim, cmap="viridis", vmin=-0.1, vmax=1.0)
    fig.colorbar(im, ax=ax, label="cosine similarity")
    ax.set_xticks(range(n)); ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n)); ax.set_yticklabels(labels, fontsize=8)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{sim[i, j]:.2f}", ha="center", va="center",
                    color="w" if sim[i, j] < 0.5 else "k", fontsize=7)
    ax.set_title("CLAP unfused: pairwise cosine similarity")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    print(f"heatmap → {out_path}")


def main():
    argv = sys.argv[1:]
    if argv == ["--selftest"]:
        return selftest()
    heatmap_out = None
    if "--heatmap" in argv:
        i = argv.index("--heatmap")
        heatmap_out = argv[i + 1]
        del argv[i:i + 2]
    paths = argv
    if len(paths) < 2:
        raise SystemExit(__doc__)

    emb = embed(paths)
    sim = emb @ emb.T  # unit-norm rows -> cosine
    names = [os.path.basename(p) for p in paths]

    if len(paths) == 2 and not heatmap_out:
        print(f"cosine similarity: {sim[0, 1]:.4f}")
    else:
        w = max(len(n) for n in names)
        print(" " * w + "  " + "  ".join(f"{n[:8]:>8}" for n in names))
        for i, n in enumerate(names):
            print(f"{n:>{w}}  " + "  ".join(f"{sim[i, j]:8.4f}" for j in range(len(names))))

    if heatmap_out:
        save_heatmap(sim, names, heatmap_out)


if __name__ == "__main__":
    main()
