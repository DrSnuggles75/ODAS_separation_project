# Bridging ODAS postfiltered audio to ROS2 (`/sss_pf`)

Goal: expose ODAS's **postfiltered** stream (bleed-suppressed) as a ROS2 topic, so we
can compare it against the raw separated `/sss`. All changes are on the **Pi**; the
devcontainer side (splitting `/sss_pf` into per-source topics) is already done in
`odas_sss.launch.py`.

Files on the Pi:
- `~/ros2_ws/src/odas_ros/odas_ros/config/cfg_uma8.cfg`
- `~/ros2_ws/src/odas_ros/odas_ros/.../lib_odas_server_node.py`

---

## 1. cfg_uma8.cfg — point the `postfiltered` block at a socket

Inside `sss:` there is a `postfiltered:` subsection (currently not a socket). Make it
mirror `separated:`, on a free port (9004):

```
    postfiltered:
    {
        fS       = 16000;
        hopSize  = 128;
        nBits    = 16;
        format   = "binary_int16";   # raw PCM, same as separated — NOT json
        gain     = 10.0;             # gain_pf — also lifts the low output level

        interface:
        {
            type = "socket";
            ip   = "127.0.0.1";
            port = 9004;
        };
    };
```

(Keep `fS`/`hopSize`/`nBits` identical to the `separated` block.)

---

## 2. lib_odas_server_node.py — add a PostfilterSocketServer

Paste this class right AFTER the existing `SssSocketServer` class. It reuses
`SssSocketServer`'s `_handle_client`/`_send_sss` — only the config section, the topic,
and the timestamp source differ:

```python
class PostfilterSocketServer(SssSocketServer):
    """Bridge ODAS postfiltered audio (bleed-suppressed) to /sss_pf."""
    def __init__(self, node, configuration, frame_id, audio_queue_size):
        pf = configuration['sss']['postfiltered']
        SocketServer.__init__(self, node, pf['interface']['port'])
        # Node-clock stamps: do NOT share the raw/sss timestamp queue (single-consumer).
        self._audio_frame_timestamp_queue = None
        self._frame_id = frame_id
        self._sss_nbits = pf['nBits']
        self._sss_format = nbits_to_format(self._sss_nbits)
        self._sss_channel_count = len(configuration['sst']['N_inactive'])
        self._sss_sampling_frequency = pf['fS']
        self._sss_frame_sample_count = pf['hopSize']
        self._sss_pub = self._node.create_publisher(AudioFrame, 'sss_pf', audio_queue_size)
```

Then, in `OdasServerNode`:

**(a)** In `__init__`, after the `self._sss_socket_server = ...` block, add:
```python
        if self._verify_postfilter_configuration():
            self._pf_socket_server = PostfilterSocketServer(
                self, self._configuration, frame_id, audio_queue_size)
        else:
            self._pf_socket_server = None
```

**(b)** Add this method next to the other `_verify_*` methods:
```python
    def _verify_postfilter_configuration(self):
        try:
            return self._configuration['sss']['postfiltered']['interface']['type'] == 'socket'
        except (KeyError, TypeError):
            return False
```

**(c)** In `run()`, after the SSS server is started, add:
```python
        if self._pf_socket_server:
            self._pf_socket_server.start()
            self.get_logger().info("Sound Source Postfilter socket server started")
```

**(d)** In the `finally:` block of `run()`, after `self._sss_socket_server.close()`, add:
```python
            if self._pf_socket_server:
                self._pf_socket_server.close()
```

---

## 3. Rebuild on the Pi

```bash
cd ~/ros2_ws
colcon build --packages-select odas_ros
source install/setup.bash
ros2 launch odas_ros odas.launch.xml
```
Look for the log line `Sound Source Postfilter socket server started`, then confirm:
```bash
ros2 topic hz /sss_pf     # ~125 Hz, channel_count 4
```

---

## 4. Devcontainer (already wired)

`odas_sss.launch.py` now splits both streams:
- `/sss`    -> `/sss/source_0…3`
- `/sss_pf` -> `/sss_pf/source_0…3`

Capture `/sss_pf` the same way, then compare:
```bash
python classify_capture.py <sss-timestamp>      # baseline (bleed)
python classify_capture.py <sss_pf-timestamp>   # postfiltered
```
Expect the cross-slot label overlap ("clapping" in both) to shrink and confidence to rise.

To capture from the postfiltered slots, point capture at the pf topics, e.g.
`ros2 run odas_vicon_tools capture_sss --topic /sss_pf/source_0 --duration 10 --output pf0.wav`
(or generalize `capture_experiment.sh` with a `--topic-prefix` — small follow-up).
