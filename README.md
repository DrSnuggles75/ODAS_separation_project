# ODAS Sound-Source Separation — Recording & Evaluation Toolkit

Tools to **record** ODAS sound-source separation trials on a miniDSP UMA microphone array
and **evaluate** them with a zero-shot audio classifier (CLAP). A trial produces the
separated per-source audio (`/sss`), an optional combined mixture, an SST angle/mapping
report, and optional rosbag + RViz video. Evaluation compares each separated source — and
the combined mixture — with CLAP fine→coarse labels and CLAP-embedding cosine similarity.

## System topology (three machines)

```
┌─────────────┐   raw mic (ALSA)   ┌──────────────────────────┐   DDS    ┌───────────────────┐
│ Raspberry   │  ───────────────>  │  ODAS + odas_ros bridge  │  ─────>  │  devcontainer     │
│ Pi + UMA    │                    │  (runs ON the Pi)        │  topics  │  (ros2_humble_ws) │
└─────────────┘                    │  publishes /ssl /sst     │          │  odas_vicon_tools │
                                   │  /sss (+ /sss_pf patch)  │          │  splits + RViz    │
                                   └──────────────────────────┘          └─────────┬─────────┘
                                                                                   │ docker exec
                                                                         ┌─────────▼─────────┐
                                                                         │  Host             │
                                                                         │  capture_experiment.sh
                                                                         │  classify_capture.py
                                                                         │  sound_similarity.py
                                                                         └───────────────────┘
```

- **Pi** — runs ODAS via `ros2 launch odas_ros odas.launch.xml`. Reads the UMA soundcard
  directly (ALSA) and publishes `/ssl` (localization), `/sst` (tracking), `/sss` (4-channel
  separated audio), optionally `/sss_pf` (postfiltered — needs the patch). Config lives here.
- **Devcontainer** (`ros2_humble_ws`) — builds the `odas_vicon_tools` package: splits the
  N-channel `/sss` into `/sss/source_0..3`, bridges Vicon → TF, drives RViz, and hosts the
  capture/analysis-helper nodes. Sees the Pi's topics over the shared ROS 2 (DDS) graph.
- **Host** — orchestrates a trial with `capture_experiment.sh` (via `docker exec` into the
  devcontainer) and runs the CLAP analysis scripts.

## Repository layout

```
ODAS_separation_project/
├── README.md                     ← you are here
├── data/                         ← recorded trials (curated by hand; committed)
└── scripts_and_other/
    ├── host/                     ← run on the host
    │   ├── capture_experiment.sh     orchestrate a trial (audio + mix + bag + video)
    │   ├── gnome_screencast.py        Wayland-safe RViz screen recorder (used by --video)
    │   ├── classify_capture.py        CLAP fine→coarse on mix + each separated slot
    │   ├── sound_similarity.py        CLAP-embedding cosine matrix + heatmap
    │   ├── clap_utils.py              shared WAV loader
    │   ├── labels/                    general_fine.txt, general_coarse.txt
    │   ├── candidate_mapping/         general_fine_to_coarse.csv
    │   └── requirements.txt
    ├── devcontainer/
    │   └── odas_vicon_tools/      ← ROS 2 package, colcon-built inside the devcontainer
    └── pi/                        ← ODAS config reference + Pi-side patch (see pi/README_CONFIG.md)
```

## Setup

### 1. Pi (ODAS)
Install one of the ODAS configs from `scripts_and_other/pi/` (`cfg_uma8.cfg` for the 7-mic
UMA-8, `cfg_uma16.cfg` for the 16-mic UMA-16 — see `pi/README_CONFIG.md`) and launch:
```bash
ros2 launch odas_ros odas.launch.xml \
    configuration_path:=/home/pi/ros2_ws/src/odas_ros/odas_ros/config/cfg_uma8.cfg
```
Optional: apply `pi/POSTFILTER_PI_PATCH.md` to also publish `/sss_pf`.
Sanity check: `ros2 topic hz /sst` and `ros2 topic hz /sss` (~125 Hz each).

### 2. Devcontainer (odas_vicon_tools)
Copy `scripts_and_other/devcontainer/odas_vicon_tools` into your `ros2_humble_ws/src/`, then:
```bash
cd ~/ros2_ws && colcon build --packages-select odas_vicon_tools && source install/setup.bash
ros2 launch odas_vicon_tools odas_sss.launch.py        # split /sss (+ /sss_pf) into per-source topics
ros2 launch odas_vicon_tools odas_vicon_viz.launch.py  # Vicon→TF + RViz (optional)
```

### 3. Host (analysis)
```bash
cd scripts_and_other/host
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
**CLAP model** (not committed, ~2 GB). Download `laion/clap-htsat-unfused` from Hugging Face
into `host/models/laion-clap-htsat-unfused` (or point `CLAP_MODEL` at it):
```bash
huggingface-cli download laion/clap-htsat-unfused --local-dir host/models/laion-clap-htsat-unfused
```
The scripts run fully offline (`HF_HUB_OFFLINE=1`).

## Recording a trial

From the host, with the devcontainer up:
```bash
./capture_experiment.sh --sources 2 --duration 10 --mix --tag pigVScrowd
```
Outputs land in `host/captures/` (move the ones you keep into `data/`), named
`<YYYY-MM-DD-HH-MM>[_<tag>]_...`:

| file | what |
|------|------|
| `_sss-source-0..3.wav` | the four separated slots (silent slots included) |
| `_mix.wav`   | combined "unseparated" reference (mean-downmix of pre-split `/sss`) — `--mix` |
| `_angles.txt`| per-slot SST azimuth/elevation, SST-id→slot mapping, pairwise separation, drift |
| `_bag/`      | rosbag of `/vicon /tf /sst /sss(_pf) ...` — `--bag` |
| `_rviz.mp4`  | RViz screen recording over the trial — `--video` |
| `_sst-timeline.txt` / `_sst.csv` | SST activity over time — `--monitor` |

Flags: `--sources N`, `--duration S`, `--mix`, `--pf` (capture `/sss_pf` instead of `/sss`),
`--bag`, `--video`, `--video-only` (record RViz only, no audio), `--monitor`, `--normalize`,
`--tag NAME`. The script auto-detects the running `ros2_humble_ws` container; the rosbag is
moved out of `$HOME/workspace/ros2_humble_ws/bags/` (adjust `HOST_WS` in the script if your
workspace path differs).

## Static targets (fix the source directions)

To take localization/tracking error out of the loop, steer the beamformer at fixed DOAs:

1. Play one source, capture its DOA off `/sst` (in the devcontainer):
   ```bash
   ros2 run odas_vicon_tools sst_target --duration 3
   ```
   It prints a paste-ready `target = ( { tag=..; x=..; y=..; z=..; }, ... );` block.
2. Paste into the Pi `cfg_uma8.cfg` `sst.target`, set `sst.add = "static"`, relaunch ODAS.
   (Unique tag per target, never `"dynamic"`; keep ≤4 targets; no trailing comma — see
   `pi/README_CONFIG.md`.) With static targets, `/sst` reports `± 0.0°` — the giveaway it took.

## Evaluating a trial (CLAP)

```bash
cd scripts_and_other/host
# fine→coarse labels for the mixture + every active slot (also writes <id>_clap.txt)
python3 classify_capture.py <RUNID>
# CLAP-embedding cosine matrix + heatmap over the slots (add _mix.wav for a mixture row)
python3 sound_similarity.py --heatmap captures/<RUNID>_cos.png \
    captures/<RUNID>_sss-source-0.wav captures/<RUNID>_sss-source-1.wav
```
`classify_capture.py` auto-includes `<RUNID>_mix.wav` (labeled `MIX (combined)`) when present.
Lower slot-to-slot cosine = better separation. Self-checks: `sound_similarity.py --selftest`,
`sst_target --self-check`.

### Adding a label
Zero-shot, so extend the vocabulary freely: add the fine label to `host/labels/general_fine.txt`
and a `fine_label,coarse_label` row to `host/candidate_mapping/general_fine_to_coarse.csv`. (E.g.
`pig oinking` → `animal` was added this way; a source with no fitting label gets misfiled into
the nearest one.)

## Key findings (what actually moves separation)

- **Level balance is the biggest lever.** Neither source should dominate; a loud source cleans
  its own slot but degrades and bleeds into the quiet one.
- **Keep sources at mic height.** The UMA is a planar array; off-plane (elevated) sources
  separate poorly. The penalty is direction-symmetric (mic-above ≈ sources-above) and depends on
  the *magnitude* of the off-plane angle. `/sst` elevation is biased/ambiguous on a planar array
  (reports ~+30° even in-plane) — don't trust it.
- **Source acoustic distinctness matters.** Very different sources (pig vs singing) separate and
  score better than similar ones, even at worse geometry.
- **CLAP can't distinguish same-class sources.** Two voices (man vs woman) saturate both labels
  and cosine (~0.96) regardless of separation quality — CLAP scores semantic class, not speaker
  identity. Use CLAP only for cross-class pairs; use speaker embeddings / ASR for voice-vs-voice.
- **`sss.mode_sep` = `dds` or `dgss` only** on this ODAS build; `dmvdr` silently kills
  odas_core_node → empty topics. `dgss` didn't beat `dds` here (mostly lowered level).

## Gotchas

- **CLAP model** is not in the repo — download it (above) or set `CLAP_MODEL`.
- **Pi configs** (`cfg_uma8.cfg`, `cfg_uma16.cfg`) are in `scripts_and_other/pi/` — both default
  to `add = "dynamic"`; uncomment `#add = "static"` + fill `sst.target` for fixed DOAs.
- **USB array card number drifts** across reboots (`hw:CARD=N`) — symptom of a wrong card is
  "topics exist but no data". Fix: pin the card *name* with the udev rule in
  `scripts_and_other/pi/alsa_card_udev/` (works for any USB audio device) and address it as
  `hw:CARD=<NAME>,DEV=0`.
- **RViz video on GNOME Wayland**: x11grab records black; `gnome_screencast.py` uses GNOME
  Shell's screencast and must run under the **system** `/usr/bin/python3` (has PyGObject), not a
  venv python. Handled by `capture_experiment.sh`.
- **libconfig parse errors** (missing `;`, trailing comma) silently produce empty topics —
  validate configs with `odaslive -v -c <cfg>` before relaunching.
