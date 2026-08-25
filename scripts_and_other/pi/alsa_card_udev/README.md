# Pin a USB audio device's ALSA card name (fix card-index drift)

Problem: a USB microphone array enumerates as a different ALSA card number (`card1`,
`card3`, ...) depending on USB probe order, which silently breaks ODAS whenever the `.cfg`
hardcodes a numeric `card = N` (or `hw:CARD=N,DEV=0`). The fix below pins the card's
**name** instead, so the `.cfg` never needs to change again.

**Works for any USB audio interface** — UMA-8, UMA-16, ReSpeaker, etc. You supply the
device's USB VID/PID and the stable name you want; nothing here is UMA-8-specific. The
worked example uses the miniDSP UMA-8 (`VID:PID = 2752:001d`, name `UMA8`); substitute your
own device's values.

All steps run **on the Pi**.

## Step 1 — find the device's current card number
```bash
cat /proc/asound/cards
```
Note the index for your array (whatever it currently is).

## Step 2 — find its USB vendor/product ID
```bash
chmod +x find_card_ids.sh
./find_card_ids.sh <card_number_from_step_1>
```
Scan the dump for the **first** block containing both `ATTRS{idVendor}=="...."` and
`ATTRS{idProduct}=="...."` — that's the device's own USB descriptor. (Ignore pairs further
down; those are upstream USB hubs.) Write down both hex values.

## Step 3 — install the udev rule
```bash
chmod +x install_card_udev_rule.sh
sudo ./install_card_udev_rule.sh <idVendor> <idProduct> [CARD_NAME]
# example (UMA-8):  sudo ./install_card_udev_rule.sh 2752 001d UMA8
# CARD_NAME defaults to UMA8; use e.g. RESPEAKER, UMA16, MYARRAY for other devices.
```
This writes `/etc/udev/rules.d/90-<name>.rules`:
```
SUBSYSTEM=="sound", KERNEL=="card*", ATTRS{idVendor}=="<VID>", ATTRS{idProduct}=="<PID>", ATTR{id}="<CARD_NAME>"
```
and reloads/retriggers udev. If the rename doesn't apply immediately, unplug/replug the
device's USB cable.

## Step 4 — verify
```bash
chmod +x verify_card.sh
./verify_card.sh [CARD_NAME]        # defaults to UMA8
```
Should show your card name in `/proc/asound/cards` regardless of its numeric index.
**Reboot the Pi and re-run this** to confirm it survives a real boot:
```bash
sudo reboot
# after it comes back:
./verify_card.sh <CARD_NAME>
```

## Step 5 — point ODAS at the stable name instead of the index
In the live `.cfg`, set the `raw.interface` block to the name-based form:
```
raw:
{
    ...
    interface:
    {
        type = "soundcard_name";
        devicename = "hw:CARD=<CARD_NAME>,DEV=0";
    }
}
```
If it currently uses `type = "soundcard"; card = N;`, replace both lines with the two
above. If it already uses `soundcard_name` with a numeric `hw:CARD=<number>`, just swap the
number for `<CARD_NAME>`.

## Step 6 — sanity-test capture before trusting it to ODAS
```bash
arecord -D hw:CARD=<CARD_NAME>,DEV=0 -f S16_LE -r 16000 -c <channels> -d 3 /tmp/test.wav
```
Set `-c` to your array's channel count (UMA-8 exposes 7 mic channels). If this records
without error, the name-based device resolves correctly.

## Step 7 — re-launch and confirm from the laptop
Start ODAS on the Pi as usual, then from the laptop devcontainer:
```bash
docker exec <container> bash -c 'source /opt/ros/humble/setup.bash && source /ros2_ws/install/setup.bash && timeout 8 ros2 topic hz /sss'
```
A steady rate confirms audio is actually flowing again.

## Notes / edge cases
- **Two identical units** (same VID:PID) can't be told apart by VID:PID alone. Re-run
  `find_card_ids.sh` and also note `ATTRS{serial}` in the dump, then add
  `ATTRS{serial}=="<value>"` to the rule.
- If your chosen name **collides** with an existing card id, the kernel appends a suffix
  (e.g. `UMA8_1`); check `/proc/asound/cards` and match the `.cfg` devicename to it.
- This fixes *device addressing* drift only, not a physically swapped-in different unit
  (a new unit of the same model still matches via VID:PID — usually what you want).
