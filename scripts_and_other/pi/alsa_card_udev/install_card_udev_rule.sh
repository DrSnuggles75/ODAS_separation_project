#!/usr/bin/env bash
# Run on the Pi as root. Writes a udev rule that pins a USB audio device's ALSA card
# *name* (not its numeric index) so it survives reboots/replugs/enumeration drift.
# Works for ANY USB audio interface — just pass its VID/PID and the name you want.
#
# Usage: sudo ./install_card_udev_rule.sh <idVendor> <idProduct> [card_id_name]
#
# Get <idVendor>/<idProduct> from find_card_ids.sh first.
# card_id_name is the stable name to assign (default UMA8; use e.g. RESPEAKER, MYARRAY).

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root (sudo)." >&2
  exit 1
fi

if [ $# -lt 2 ]; then
  echo "Usage: $0 <idVendor> <idProduct> [card_id_name]" >&2
  exit 1
fi

VID="$1"
PID="$2"
NAME="${3:-UMA8}"
RULE_FILE="/etc/udev/rules.d/90-${NAME,,}.rules"

cat > "$RULE_FILE" <<EOF
SUBSYSTEM=="sound", KERNEL=="card*", ATTRS{idVendor}=="${VID}", ATTRS{idProduct}=="${PID}", ATTR{id}="${NAME}"
EOF

echo "Wrote ${RULE_FILE}:"
cat "$RULE_FILE"
echo

udevadm control --reload-rules
udevadm trigger --subsystem-match=sound

echo "Reloaded udev rules and re-triggered the sound subsystem."
echo "If the card doesn't show the new name yet, physically unplug/replug the device (or reboot)."
echo "Then verify with: ./verify_card.sh ${NAME}"
