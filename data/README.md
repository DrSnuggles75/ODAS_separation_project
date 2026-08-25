# Data

The recorded trials (separated WAVs, `_mix.wav`, `_angles.txt`, `_clap.txt`, `_cos.png`,
RViz videos, rosbags) are **not stored in this git repo** — they're too large. They live in
cloud storage, **available on request**.

## Access

The full dataset is hosted in cloud storage; **access is granted upon request**. Contact the
repository owner (see the repository/GitHub profile) to be given access. Once granted,
download the capture subdirectories and unpack them back into this `data/` folder so the
analysis scripts and the paths referenced in the docs resolve.

## Layout (once downloaded)

```
data/
├── README.md              ← this file (tracked in git)
├── Experiment setup/      ← how the trials were physically set up (tracked in git)
├── UMA_8/                 ← UMA-8 captures            (cloud only)
├── UMA_16/                ← UMA-16 captures           (cloud only)
└── Respeaker_4micArray/   ← ReSpeaker captures        (cloud only)
```

Only `README.md` and `Experiment setup/` are committed; everything else is gitignored and
must be requested (see **Access** above).

## Re-running the analysis

Point the host analysis scripts at a downloaded capture (see the top-level `README.md`):
```bash
cd scripts_and_other/host
python3 classify_capture.py <path-or-runid>
python3 sound_similarity.py --heatmap out.png <capture>_sss-source-0.wav <capture>_sss-source-1.wav
```
