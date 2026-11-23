"""High-level board classes: DroidBoard and BeaconBoard."""

import threading
import time

from .errors import BoardTimeout, ProtocolError
from .link import DEFAULT_BAUDRATE, Link
from .models import (BeaconStatus, BeepResult, BoardInfo, Diagnosis, DroidStatus, Sound)

# Timeouts (seconds) for commands that legitimately take a while.
_T_CONNECT = 30.0
_T_CHECK = 120.0  # the library may retry a few times
_T_DIAGNOSE = 70.0
_T_BEEP = 30.0
_T_HEAD = 30.0
_T_DEMO = 90.0
_T_REBOOT = 15.0


class Board:
    """Common behaviour. Opening a board performs the ``hello`` handshake.

    Use as a context manager, or call :meth:`close`. Methods are blocking and
    thread-safe; see ``astromech_boards.aio`` for asyncio wrappers.
    """

    ROLE = None

    def __init__(self, port=None, *, baudrate=DEFAULT_BAUDRATE, link=None, handshake_timeout=6.0):
        self._link = link or Link(port, baudrate=baudrate, handshake_timeout=handshake_timeout)
        self.port = self._link.port
        self.info = BoardInfo.from_dict(self._link.hello)
        if self.ROLE and self.info.role != self.ROLE:
            self._link.close()
            raise ProtocolError("%s is a %r board, not %r" % (self.port, self.info.role, self.ROLE))

    # ---- lifecycle -------------------------------------------------------

    def close(self):
        self._link.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def closed(self):
        return self._link.closed

    def on_event(self, callback):
        """Register ``callback(event_dict)`` for board events (boot, droid_state,
        log, disconnected). Runs on the reader thread. Returns an unregister function."""
        return self._link.add_event_listener(callback)

    # ---- common commands -------------------------------------------------

    def ping(self):
        """Round-trip time to the board in seconds."""
        t0 = time.monotonic()
        self._link.request("ping", timeout=5.0)
        return time.monotonic() - t0

    def reboot(self, wait=True, timeout=_T_REBOOT):
        """Restart the board. With ``wait`` (default) returns once it has booted again."""
        booted = threading.Event()
        remove = self.on_event(lambda e: booted.set() if e.get("event") == "boot" else None)
        try:
            self._link.request("reboot", timeout=5.0)
            if not wait:
                return
            if not booted.wait(timeout):
                raise BoardTimeout("board did not report boot within %.0f s" % timeout)
        finally:
            remove()
        self.info = BoardInfo.from_dict(self._link.request("hello", timeout=5.0))

    def factory_reset(self, wait=True, timeout=_T_REBOOT):
        """Erase all saved settings and restart."""
        booted = threading.Event()
        remove = self.on_event(lambda e: booted.set() if e.get("event") == "boot" else None)
        try:
            self._link.request("factory_reset", timeout=5.0)
            if wait and not booted.wait(timeout):
                raise BoardTimeout("board did not report boot within %.0f s" % timeout)
        finally:
            remove()
        if wait:
            self.info = BoardInfo.from_dict(self._link.request("hello", timeout=5.0))

    def get_config(self):
        """Saved settings (what the board will use after its next boot)."""
        return self._link.request("get_config", timeout=5.0)


class DroidBoard(Board):
    """A board that controls exactly one droid over BLE.

    Commands that talk to the droid raise :class:`DroidUnavailable` if it can't
    be reached, and :class:`NotConfigured` if no address has been set.
    """

    ROLE = "droid"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._droid_connected = threading.Event()
        self.on_event(self._track_state)
        try:
            if self.status().connected:
                self._droid_connected.set()
        except Exception:
            self.close()
            raise

    def _track_state(self, e):
        if e.get("event") == "droid_state":
            if (e.get("data") or {}).get("connected"):
                self._droid_connected.set()
            else:
                self._droid_connected.clear()

    # ---- configuration ---------------------------------------------------

    def configure(self, *, address=None, type=None, personality=None, alias=None, restart=True):
        """Save droid settings. They take effect after a reboot, which happens
        here unless ``restart=False``. Returns the saved config."""
        args = {k: v for k, v in (("address", address), ("type", type),
                                  ("personality", personality), ("alias", alias)) if v is not None}
        self._link.request("set_config", args, timeout=5.0)
        if restart:
            self.reboot()
            self._droid_connected.clear()
        return self.get_config()

    # ---- state -----------------------------------------------------------

    def status(self):
        return DroidStatus.from_dict(self._link.request("status", timeout=5.0))

    @property
    def droid_connected(self):
        """Last known BLE state, kept current by the board's ``droid_state`` events."""
        return self._droid_connected.is_set()

    def wait_for_droid(self, timeout=30.0):
        """Block until the droid is connected. Returns False on timeout."""
        return self._droid_connected.wait(timeout)

    def sounds(self):
        """The personality's sound bank, indexed as ``beep(sound=...)`` expects."""
        r = self._link.request("sounds", timeout=5.0)
        return [Sound(**s) for s in r["sounds"]]

    # ---- connection ------------------------------------------------------

    def connect(self, timeout=_T_CONNECT):
        """Connect now (the board also connects and reconnects by itself)."""
        r = self._link.request("connect", timeout=timeout)
        return r.get("connect_ms")

    def disconnect(self):
        """Drop the BLE link and stop auto-reconnecting until :meth:`connect`."""
        self._link.request("disconnect", timeout=10.0)

    def check_alive(self, timeout=_T_CHECK):
        """Ping the droid, reconnecting if needed. True if it answered."""
        return bool(self._link.request("check", timeout=timeout)["available"])

    def diagnose(self, timeout=_T_DIAGNOSE):
        """Scan for the droid, try to connect and ping. Returns a :class:`Diagnosis`."""
        return Diagnosis.from_dict(self._link.request("diagnose", timeout=timeout))

    # ---- actions ---------------------------------------------------------

    def beep(self, sound, *, turn_head=False, wait=False, timeout=_T_BEEP):
        """Play personality sound number ``sound``. With ``turn_head`` (R-series)
        the head looks around meanwhile and the call returns when it is done.
        With ``wait`` the call returns after the clip has finished."""
        args = {"sound": sound}
        if turn_head:
            args["turn_head"] = True
        if wait:
            args["wait"] = True
        r = self._link.request("beep", args, timeout=timeout)
        return BeepResult(ms=r["ms"], turn_head=r["turn_head"])

    def play(self, group, sound, timeout=_T_BEEP):
        """Play clip ``sound`` of audio group ``group`` (0-255 each), bypassing the personality.
        Returns once the droid has been told to play; it does not wait for the clip to end."""
        self._link.request("play", {"group": group, "sound": sound}, timeout=timeout)

    def set_volume(self, level):
        """Droid volume, 0-31."""
        self._link.request("volume", {"level": level}, timeout=_T_BEEP)

    def center_head(self, timeout=_T_HEAD):
        self._link.request("center_head", timeout=timeout)

    def look_around(self, timeout=_T_HEAD):
        """Head left, right, centre (about 3 s)."""
        self._link.request("look_around", timeout=timeout)

    def move(self, direction, ms, *, speed=None, timeout=None):
        """Drive the wheels for ``ms`` milliseconds (1-5000), then stop.

        ``direction`` is one of ``forward``, ``backward``, ``spin_cw``,
        ``spin_ccw``, ``turn_cw``, ``turn_ccw`` (BB units: forward/backward only).
        ``speed`` is 1-255 (droid default if omitted). THIS MOVES THE DROID:
        make sure it is somewhere safe. Call :meth:`stop` to halt it early
        from another thread.
        """
        args = {"direction": direction, "ms": ms}
        if speed is not None:
            args["speed"] = speed
        self._link.request("move", args, timeout=timeout or (ms / 1000.0 + 30.0))

    def stop(self):
        """Stop the wheels immediately (answered even while a move is running)."""
        self._link.request("stop", timeout=10.0)

    def motor(self, motor, speed, *, backward=False, ramp_ms=None):
        """Start, change or stop one wheel. ``motor`` is ``left`` or ``right``; ``speed`` 0-255
        (0 stops it). The wheel keeps running until the next call or :meth:`stop`: THIS MOVES THE
        DROID, so make sure it is somewhere safe."""
        args = {"motor": motor, "speed": speed, "backward": bool(backward)}
        if ramp_ms is not None:
            args["ramp_ms"] = ramp_ms
        self._link.request("motor", args, timeout=10.0)

    def rotate_head(self, direction, timeout=_T_HEAD):
        """Turn the head ``left`` or ``right`` for 1.5 s, then stop it (R-series only)."""
        self._link.request("rotate_head", {"direction": direction}, timeout=timeout)

    def demo(self, timeout=_T_DEMO):
        """Centre head, look around while playing the first 7 sounds, centre head.
        Head only; never drives the wheels."""
        self._link.request("demo", timeout=timeout)


class BeaconBoard(Board):
    """A board that broadcasts the keep-awake beacon.

    It starts from its saved configuration at power-on, so a master is only
    needed to change or inspect it.
    """

    ROLE = "beacon"

    def status(self):
        return BeaconStatus.from_dict(self._link.request("status", timeout=5.0))

    def set_beacon(self, kind="silent", *, location_id=None, persist=True):
        """Switch beacon type now. ``kind`` is ``"silent"`` (keeps droids awake and
        calm) or ``"location"`` (needs ``location_id`` 0-255 the first time).
        ``persist`` saves it for the next power-on."""
        args = {"kind": kind, "persist": persist}
        if location_id is not None:
            args["location_id"] = location_id
        return BeaconStatus.from_dict(self._link.request("set_beacon", args, timeout=5.0))

    def stop(self):
        """Stop broadcasting until :meth:`start` (or a reboot)."""
        return BeaconStatus.from_dict(self._link.request("stop_beacon", timeout=5.0))

    def start(self):
        return BeaconStatus.from_dict(self._link.request("start_beacon", timeout=5.0))
