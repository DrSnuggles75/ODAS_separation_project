#!/usr/bin/env python3
"""Record a screen region via GNOME Shell's built-in screencast (Wayland-safe).

GNOME aborts a screencast the moment the calling D-Bus sender vanishes, so a
`gdbus call` (which exits immediately) never records. This holds ONE connection
open, starts the recording, then waits for SIGINT/SIGTERM to stop it — tying the
video length to the caller's lifetime.

    gnome_screencast.py X Y W H OUTBASE     # records region until signalled
    # prints the actual file path GNOME used (it picks the extension) on start
"""
import signal
import sys

import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib

IFACE = 'org.gnome.Shell.Screencast'
PATH = '/org/gnome/Shell/Screencast'


def main():
    x, y, w, h = map(int, sys.argv[1:5])
    outbase = sys.argv[5]
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    opts = {'framerate': GLib.Variant('i', 15), 'draw-cursor': GLib.Variant('b', False)}
    ok, fname = bus.call_sync(
        IFACE, PATH, IFACE, 'ScreencastArea',
        GLib.Variant('(iiiisa{sv})', (x, y, w, h, outbase, opts)),
        None, Gio.DBusCallFlags.NONE, -1, None).unpack()
    if not ok:
        print('screencast failed to start', file=sys.stderr)
        sys.exit(1)
    print(fname, flush=True)   # actual path (GNOME chooses the extension)

    def _stop(*_):
        bus.call_sync(IFACE, PATH, IFACE, 'StopScreencast',
                      None, None, Gio.DBusCallFlags.NONE, -1, None)
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    signal.pause()   # keep the sender (this connection) alive until signalled


if __name__ == '__main__':
    main()
