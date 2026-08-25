#!/usr/bin/env bash
# Run on the Pi. Dumps the full udev attribute chain for a given ALSA card,
# so you can read off the idVendor/idProduct of its USB ancestor.
#
# Usage: ./find_card_ids.sh <alsa_card_number>
#
# If you don't know the card number yet, run with no args to list current cards.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <alsa_card_number>"
  echo
  echo "Current ALSA cards:"
  cat /proc/asound/cards
  exit 1
fi

CARD="$1"
DEV="/dev/snd/controlC${CARD}"

if [ ! -e "$DEV" ]; then
  echo "No such device: $DEV" >&2
  echo "Current ALSA cards:" >&2
  cat /proc/asound/cards >&2
  exit 1
fi

SYSPATH="$(udevadm info -q path -n "$DEV")"

echo "### Device: $DEV"
echo "### udev path: $SYSPATH"
echo "###"
echo "### Look at the FIRST 'looking at parent device' block below that contains"
echo "### both ATTRS{idVendor} and ATTRS{idProduct} -- those are the values you need."
echo "### (There may be other idVendor/idProduct pairs further down for USB hubs"
echo "###  upstream of the device -- ignore those, use the closest/first one.)"
echo
udevadm info -a -p "$SYSPATH"
