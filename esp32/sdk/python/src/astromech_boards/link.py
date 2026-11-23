"""Low-level transport: newline-delimited JSON over a serial port.

One reader thread parses incoming lines. Lines that are not JSON objects
(ROM boot text, noise) are ignored. Responses are matched to requests by id,
so requests may be issued from several threads at once; events are delivered
to listeners on the reader thread (keep callbacks short and non-blocking).
"""

import concurrent.futures
import itertools
import json
import logging
import threading
import time

from .errors import BoardTimeout, Disconnected, ProtocolError, board_error

log = logging.getLogger(__name__)

PROTOCOL_MAJOR = 1
DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 15.0


def open_serial(port, baudrate=DEFAULT_BAUDRATE):
    """Open a port without asserting DTR/RTS, which would reset most dev boards."""
    import serial

    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baudrate
    ser.timeout = 0.1
    ser.write_timeout = 2.0
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


class Link:
    """A connection to one board.

    ``serial_obj`` may be any object with ``read(n)``, ``write(bytes)`` and
    ``close()`` (``read`` must return after a short timeout); it is used by the
    tests. Otherwise ``port`` is opened with pyserial.
    """

    def __init__(self, port=None, *, baudrate=DEFAULT_BAUDRATE, serial_obj=None,
                 handshake_timeout=6.0):
        if serial_obj is None and port is None:
            raise ValueError("port or serial_obj is required")
        self.port = port
        self._ser = serial_obj if serial_obj is not None else open_serial(port, baudrate)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending = {}
        self._listeners = []
        self._closed = False
        self._error = None
        self._reader = threading.Thread(target=self._read_loop, name="astromech-link", daemon=True)
        self._reader.start()
        try:
            self.hello = self._handshake(handshake_timeout)
        except Exception:
            self.close()
            raise

    # ---- public ----------------------------------------------------------

    @property
    def closed(self):
        return self._closed

    def request(self, cmd, args=None, timeout=DEFAULT_TIMEOUT):
        """Send a command and return its result dict.

        Raises a BoardError subclass if the board refuses, BoardTimeout if there
        is no answer in ``timeout`` seconds, Disconnected if the link is gone.
        """
        req_id = next(self._ids)
        fut = concurrent.futures.Future()
        with self._lock:
            if self._closed:
                raise Disconnected(str(self._error or "link is closed"))
            self._pending[req_id] = fut
        msg = {"id": req_id, "cmd": cmd}
        if args:
            msg["args"] = args
        try:
            self._write(msg)
            return fut.result(timeout)
        except concurrent.futures.TimeoutError:
            raise BoardTimeout("no answer to %r within %.1f s" % (cmd, timeout)) from None
        finally:
            with self._lock:
                self._pending.pop(req_id, None)

    def add_event_listener(self, callback):
        """Call ``callback(event_dict)`` for every event. Returns a function that removes it."""
        with self._lock:
            self._listeners.append(callback)

        def remove():
            with self._lock:
                if callback in self._listeners:
                    self._listeners.remove(callback)

        return remove

    def close(self):
        self._shutdown(None)
        try:
            self._ser.close()
        except Exception:  # pragma: no cover - best effort
            pass
        if threading.current_thread() is not self._reader:
            self._reader.join(timeout=2.0)

    # ---- internals -------------------------------------------------------

    def _handshake(self, timeout):
        """Ask for ``hello`` until the board answers (it may still be booting)."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                info = self.request("hello", timeout=min(0.75, max(0.05, deadline - time.monotonic())))
                break
            except BoardTimeout:
                if time.monotonic() >= deadline:
                    raise BoardTimeout("no answer from the board on %s" % (self.port or "serial")) from None
        if info.get("protocol") != PROTOCOL_MAJOR:
            raise ProtocolError("board speaks protocol %r, this SDK speaks %d"
                                % (info.get("protocol"), PROTOCOL_MAJOR))
        return info

    def _write(self, msg):
        data = (json.dumps(msg, separators=(",", ":")) + "\n").encode()
        try:
            with self._write_lock:
                self._ser.write(data)
        except Exception as e:
            self._shutdown(e)
            raise Disconnected(str(e)) from e

    def _read_loop(self):
        buf = bytearray()
        while not self._closed:
            try:
                chunk = self._ser.read(256)
            except Exception as e:
                self._shutdown(e)
                return
            if not chunk:
                continue
            buf += chunk
            while True:
                nl = buf.find(b"\n")
                if nl < 0:
                    break
                line = bytes(buf[:nl]).strip()
                del buf[:nl + 1]
                self._handle_line(line)
            if len(buf) > 65536:  # runaway junk without a newline
                buf.clear()

    def _handle_line(self, line):
        if not line.startswith(b"{"):
            log.debug("ignoring non-protocol line: %r", line[:80])
            return
        try:
            msg = json.loads(line)
        except ValueError:
            log.debug("ignoring malformed line: %r", line[:80])
            return
        if not isinstance(msg, dict):
            return
        if "event" in msg:
            self._dispatch_event(msg)
            return
        req_id = msg.get("id")
        with self._lock:
            fut = self._pending.get(req_id)
        if fut is None:
            if req_id is not None:
                log.debug("response for unknown/expired id %r", req_id)
            else:
                log.warning("board rejected a line: %s", msg.get("error"))
            return
        if msg.get("ok"):
            fut.set_result(msg.get("result") or {})
        else:
            e = msg.get("error") or {}
            fut.set_exception(board_error(e.get("code", "internal"), e.get("message", "")))

    def _dispatch_event(self, msg):
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(msg)
            except Exception:
                log.exception("event listener failed")

    def _shutdown(self, error):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._error = error
            pending = list(self._pending.values())
            self._pending.clear()
        for fut in pending:
            if not fut.done():
                fut.set_exception(Disconnected(str(error or "link closed")))
        if error is not None:
            self._dispatch_event({"event": "disconnected", "data": {"error": str(error)}})
