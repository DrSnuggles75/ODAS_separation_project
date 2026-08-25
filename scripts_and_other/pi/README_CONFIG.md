# Pi-side ODAS config

The **actual working ODAS configs** used for the recordings, copied from the Pi
(`~/ros2_ws/src/odas_ros/odas_ros/config/`):

- **`cfg_uma8.cfg`** — the 7-mic **UMA-8** array (`nChannels = 8`, `hw:CARD=UMA8,DEV=0`).
- **`cfg_uma16.cfg`** — the 16-mic **UMA-16** array (`nChannels = 16`, `aux0..aux15` channelmap;
  its `mu` grid is the geometry built/rotated during this project).

Both ship with `sst.add = "dynamic"` active and `#add = "static"` commented — uncomment the
static line (and fill `sst.target`) to switch to fixed DOAs. Both use `sss.mode_sep = "dds"`,
`mode_pf = "ss"`, `theta_new = 0.7`, `N_inactive = (150,150,150,150)`. Launch one with:

```bash
cd ros2_ws

source install/setup.bash

ros2 launch odas_ros odas.launch.xml

or
ros2 launch odas_ros odas.launch.xml configuration_path:=<abs-path>/<config_file_name.cfg>
```

What the config defines, per trial:
- **`raw`** — the UMA soundcard (`type = "soundcard_name"`, `devicename = "hw:CARD=UMA8,DEV=0"`).
  The raw ALSA card **number** drifts across reboots, so pin the card **name** with the udev
  rule in [`alsa_card_udev/`](alsa_card_udev/README.md) (works for any USB array) and address
  it as `hw:CARD=UMA8,DEV=0` instead of a number. (For the UMA-8 the rule keys on its USB
  VID:PID `2752:001d`.)
- **`mics` / `mu`** — the microphone geometry. Two arrays were used: the 7-mic UMA-8 and a
  16-mic UMA-16 `mu` grid (the latter built during this project; a −90° xy rotation was applied
  as `(x, y, z) → (-y, x, z)`).
- **`sst.add`** — `"dynamic"` (auto-track) vs `"static"` (fixed target DOAs).
- **`sst.target`** — the static target DOA list, e.g.:
  ```
  target = (
    { tag = "LAPTOP_AREA"; x = 0.8545; y = 0.0848; z = 0.5124; },
    { tag = "TABLET";      x = -0.8480; y = -0.1280; z = 0.5146; }
  );
  ```
- **`sss.mode_sep`** — `"dds"` or `"dgss"` ONLY on this build (`"dmvdr"` silently kills
  odas_core_node → empty topics).

## Reference material in this folder

- **`UMA_8_annotated_clean.cfg`** — a heavily annotated ODAS config (paper references per
  parameter). Use it as the reference when editing `cfg_uma8.cfg`.
- **`POSTFILTER_PI_PATCH.md`** — how to expose ODAS's postfiltered stream as `/sss_pf`
  (optional Pi-side patch; needed only if you want to capture with `--pf`).

## libconfig gotchas (both cost real debugging time)

- Every statement in a group needs a trailing `;` (e.g. `add = "static";`).
- **No trailing comma** after the last entry in a `( ... )` list — ODAS's libconfig rejects it.
- After any edit, validate before relaunching the ROS stack:
  ```bash
  ~/ros2_ws/build/odas_ros/src/odas/bin/odaslive -v -c <config>.cfg
  ```
  It prints the parse error with a line number that `ros2 launch` hides.
