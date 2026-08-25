#!/usr/bin/env bash
# Run on the Pi. Confirms the device is showing up under its pinned name.
#
# Usage: ./verify_card.sh [card_id_name]

set -euo pipefail

NAME="${1:-UMA8}"

echo "### /proc/asound/cards ###"
cat /proc/asound/cards
echo

if grep -qi "$NAME" /proc/asound/cards; then
  echo "OK: card '${NAME}' is present."
else
  echo "NOT FOUND: '${NAME}' is not present yet."
  echo "Try replugging the device's USB cable, or reboot, then re-run this script."
fi

echo
echo "### arecord -L entries matching ${NAME} ###"
arecord -L | grep -i "$NAME" || echo "(none yet)"
