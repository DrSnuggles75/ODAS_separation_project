#!/usr/bin/env bash
# Capture SSS sources from the devcontainer and save with timestamped filenames.
# Optionally record a rosbag (Vicon GT + ODAS topics) and an RViz screen video
# over the same trial window — one command per sweep trial.
#
# Usage:
#   ./capture_experiment.sh                             # 4 sources, 5 seconds
#   ./capture_experiment.sh --sources 2 --duration 10
#   ./capture_experiment.sh --sources 2 --normalize     # normalize to full scale
#   ./capture_experiment.sh --sources 2 --monitor       # also log SST activity over time
#   ./capture_experiment.sh --sources 2 --pf            # capture postfiltered stream
#   ./capture_experiment.sh --sources 2 --mix           # also save combined mixture (/sss downmix)
#   ./capture_experiment.sh --sources 2 --duration 10 --tag dds-30deg --bag --video
#     # sweep trial: WAVs+angles + rosbag of /vicon /tf /sst /sss(_pf) + RViz .mp4
set -e

SOURCES=4
DURATION=5
NORMALIZE=""
MONITOR=""
STREAM="sss"      # --pf switches to the postfiltered stream
TAG=""
BAG=""
VIDEO=""
VIDEO_ONLY=""
MIX=""
# Vicon GT + ODAS topics for the trial bag (regex from record_experiment.launch.py + sss_pf).
BAG_REGEX='^/ssl$|^/sst$|^/sst_poses$|^/ssl_pcl2$|^/sss(_pf)?$|^/sss(_pf)?/source_[0-9]+$|^/tf$|^/tf_static$|^/vicon/.*'
CAPTURES_DIR="$(dirname "$0")/captures"
HOST_WS="$HOME/workspace/ros2_humble_ws"   # mounted as /ros2_ws in the container

while [[ $# -gt 0 ]]; do
  case $1 in
    --sources)   SOURCES="$2";  shift 2 ;;
    --duration)  DURATION="$2"; shift 2 ;;
    --normalize) NORMALIZE="--normalize"; shift ;;
    --monitor)   MONITOR="1"; shift ;;
    --pf)        STREAM="sss_pf"; shift ;;
    --tag)       TAG="$2"; shift 2 ;;
    --bag)       BAG="1"; shift ;;
    --video)     VIDEO="1"; shift ;;
    --video-only) VIDEO_ONLY="1"; VIDEO="1"; shift ;;
    --mix)       MIX="1"; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# Container only needed for the audio/bag half — skip detection in video-only mode.
if [[ -z "$VIDEO_ONLY" ]]; then
  # Auto-detect the ros2_humble_ws devcontainer (name changes on every rebuild).
  CONTAINER=$(docker ps --format '{{.Names}}\t{{.Image}}' | grep ros2_humble_ws | head -1 | cut -f1)
  if [[ -z "$CONTAINER" ]]; then
    echo "No running ros2_humble_ws devcontainer found (is it up?)." >&2
    exit 1
  fi
fi

RUNID=$(date +"%Y-%m-%d-%H-%M")
[[ -n "$TAG" ]] && RUNID="${RUNID}_${TAG}"
TMP_PREFIX="/tmp/sss_${RUNID}"

mkdir -p "$CAPTURES_DIR"

# --- RViz screen recording (host side) ---------------------------------------
# GNOME Wayland: x11grab records black. Use GNOME Shell's built-in screencast via a
# helper that holds ONE D-Bus connection open for the whole recording (GNOME aborts
# the moment the caller vanishes). Needs system python3 (has PyGObject); the mise
# python does not. Started here, signalled to stop after the capture completes.
if [[ -n "$VIDEO" ]]; then
  SCREENCAST="$(dirname "$0")/gnome_screencast.py"
  VIDEO_BASE="$(cd "$CAPTURES_DIR" && pwd)/${RUNID}_rviz"   # GNOME picks the extension
  VIDEO_NAME_FILE="${TMPDIR:-/tmp}/${RUNID}_vidname"
  # Locate the RViz window by its WM_CLASS (rviz2), picking the widest such window (the
  # main view, not the tiny helper/selection windows). Read absolute geometry straight
  # from `xwininfo -id` — the tree's inline geometry breaks on monitors at negative
  # coords (e.g. "+-25+-25") and can pick the decoration frame instead of the content.
  RVIZ_ID=$(xwininfo -root -tree 2>/dev/null | awk '/\("rviz2" "rviz2"\)/{for(i=1;i<=NF;i++) if($i ~ /^[0-9]+x[0-9]+/){split($i,a,"x"); if(a[1]+0>maxw){maxw=a[1]+0; id=$1}}} END{print id}')
  G=$(xwininfo -id "$RVIZ_ID" 2>/dev/null)
  X=$(awk '/Absolute upper-left X/{print $NF}' <<<"$G")
  Y=$(awk '/Absolute upper-left Y/{print $NF}' <<<"$G")
  W=$(awk '/^  Width/{print $NF}' <<<"$G")
  H=$(awk '/^  Height/{print $NF}' <<<"$G")
  if [[ -n "$RVIZ_ID" && -n "$W" && -n "$H" ]]; then
    # ponytail: coords are the compositor logical layout (scale 1 here); RViz must stay
    # unmoved/unoccluded on that monitor during the trial.
    /usr/bin/python3 "$SCREENCAST" "$X" "$Y" "$W" "$H" "$VIDEO_BASE" >"$VIDEO_NAME_FILE" 2>&1 &
    VIDEO_PID=$!
  else
    echo "WARNING: no RViz window found — skipping video (is RViz open?)." >&2
    VIDEO=""
  fi
fi

# Video-only: record RViz until Ctrl-C, then report the file. No container/audio/bag.
if [[ -n "$VIDEO_ONLY" ]]; then
  [[ -z "$VIDEO_PID" ]] && exit 1          # no RViz window found (warned already)
  echo "Recording RViz (video-only) — Ctrl-C to stop."
  trap 'kill -INT "$VIDEO_PID" 2>/dev/null' INT
  wait "$VIDEO_PID" 2>/dev/null || true    # set -e: swallow SIGINT exit code
  VOUT=$(head -1 "$VIDEO_NAME_FILE" 2>/dev/null)
  { [[ -n "$VOUT" && -s "$VOUT" ]] && echo "→ $VOUT"; } || echo "WARNING: no file" >&2
  exit 0
fi

# --- Container side: bag + monitor (background) + capture (foreground) --------
INNER="source /ros2_ws/install/setup.bash; "
if [[ -n "$BAG" ]]; then
  INNER+="timeout -s INT $((DURATION + 3)) ros2 bag record --regex '$BAG_REGEX' \
    -o /ros2_ws/bags/${RUNID} > ${TMP_PREFIX}_bag.log 2>&1 & "
fi
if [[ -n "$MONITOR" ]]; then
  INNER+="ros2 run odas_vicon_tools sst_monitor \
    --duration $DURATION --csv ${TMP_PREFIX}_sst.csv > ${TMP_PREFIX}_sst_timeline.txt 2>&1 & "
fi
INNER+="ros2 run odas_vicon_tools capture_sss \
  --sources $SOURCES --duration $DURATION --prefix $TMP_PREFIX --stream $STREAM $NORMALIZE ${MIX:+--mix}; wait"

docker exec "$CONTAINER" bash -c "$INNER"

# SST ids are dynamic, so active sources can land on any slot — always pull all 4.
# The _angles.txt report says which slots are actually live.
# ponytail: keeps all 4 WAVs incl. silent slots; add _angles.txt parsing to auto-drop
# silent slots if captures/ gets cluttered.
for i in 0 1 2 3; do
  dst="${CAPTURES_DIR}/${RUNID}_sss-source-${i}.wav"
  docker cp "${CONTAINER}:${TMP_PREFIX}_source_${i}.wav" "$dst"
  echo "→ $dst"
done

# SST azimuth / mapping / drift report for this recording.
docker cp "${CONTAINER}:${TMP_PREFIX}_angles.txt" "${CAPTURES_DIR}/${RUNID}_angles.txt"
echo "→ ${CAPTURES_DIR}/${RUNID}_angles.txt"

# Combined mixture (/sss downmix; only when --mix was passed; skip quietly if not captured).
if [[ -n "$MIX" ]]; then
  if docker cp "${CONTAINER}:${TMP_PREFIX}_mix.wav" "${CAPTURES_DIR}/${RUNID}_mix.wav" 2>/dev/null; then
    echo "→ ${CAPTURES_DIR}/${RUNID}_mix.wav"
  else
    echo "WARNING: no mix WAV produced (is /${STREAM} visible in the container?)." >&2
  fi
fi

# SST activity timeline + raw CSV (only when --monitor was passed).
if [[ -n "$MONITOR" ]]; then
  docker cp "${CONTAINER}:${TMP_PREFIX}_sst_timeline.txt" "${CAPTURES_DIR}/${RUNID}_sst-timeline.txt"
  docker cp "${CONTAINER}:${TMP_PREFIX}_sst.csv" "${CAPTURES_DIR}/${RUNID}_sst.csv"
  echo "→ ${CAPTURES_DIR}/${RUNID}_sst-timeline.txt"
  echo "→ ${CAPTURES_DIR}/${RUNID}_sst.csv"
  echo "--- SST activity timeline ---"
  cat "${CAPTURES_DIR}/${RUNID}_sst-timeline.txt"
fi

# Rosbag: written under /ros2_ws (mounted), so just move it into captures/.
if [[ -n "$BAG" ]]; then
  if [[ -d "${HOST_WS}/bags/${RUNID}" ]]; then
    mv "${HOST_WS}/bags/${RUNID}" "${CAPTURES_DIR}/${RUNID}_bag"
    echo "→ ${CAPTURES_DIR}/${RUNID}_bag"
  else
    echo "WARNING: expected bag at ${HOST_WS}/bags/${RUNID} not found — see ${TMP_PREFIX}_bag.log in the container." >&2
  fi
fi

# RViz video: the helper has been recording through the capture window; stop it now.
if [[ -n "$VIDEO" ]]; then
  kill -INT "$VIDEO_PID" 2>/dev/null || true
  wait "$VIDEO_PID" 2>/dev/null || true
  VOUT=$(head -1 "$VIDEO_NAME_FILE" 2>/dev/null)
  if [[ -n "$VOUT" && -s "$VOUT" ]]; then
    echo "→ $VOUT"
  else
    echo "WARNING: screencast produced no file (see $VIDEO_NAME_FILE)." >&2
  fi
fi
