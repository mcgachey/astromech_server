"""A fake serial port with a tiny firmware simulator behind it."""

import json
import queue
import threading
import time


class FakeSerial:
    """Implements read/write/close. Commands are answered by ``handler(cmd, args)``
    which returns a result dict, raises ``Fail(code,msg)``, or returns ``None`` to
    stay silent (to test timeouts)."""

    def __init__(self, handler, boot_noise=b"rst:0x1 (POWERON_RESET)\r\n{broken\r\n", ignore_first=0):
        self.handler = handler
        self._rx = queue.Queue()
        self.closed = False
        self.written = []
        self._ignore = ignore_first  # swallow this many requests (board still booting)
        if boot_noise:
            self._rx.put(boot_noise)

    def read(self, n):
        try:
            return self._rx.get(timeout=0.05)
        except queue.Empty:
            return b""

    def write(self, data):
        for line in data.decode().splitlines():
            msg = json.loads(line)
            self.written.append(msg)
            if self._ignore:
                self._ignore -= 1
                continue
            threading.Thread(target=self._answer, args=(msg,), daemon=True).start()

    def _answer(self, msg):
        try:
            result = self.handler(msg["cmd"], msg.get("args") or {})
        except Fail as f:
            self.push({"id": msg["id"], "ok": False, "error": {"code": f.code, "message": f.message}})
            return
        if result is not None:
            self.push({"id": msg["id"], "ok": True, "result": result})

    def push(self, obj):
        self._rx.put((json.dumps(obj) + "\n").encode())

    def event(self, name, **data):
        self.push({"event": name, "data": data})

    def close(self):
        self.closed = True


class Fail(Exception):
    def __init__(self, code, message=""):
        self.code, self.message = code, message


HELLO = {"role": "droid", "firmware_version": "0.2.0", "protocol": 1,
         "device_id": "3ce90e8581f4", "uptime_ms": 1234, "build": "test"}


def droid_handler(state=None):
    state = state if state is not None else {"connected": False}

    def handle(cmd, args):
        if cmd == "hello":
            return dict(HELLO)
        if cmd == "ping":
            return {}
        if cmd == "status":
            return {"configured": True, "alias": "r2t2", "address": "F7:E6:74:95:E5:53",
                    "type": "r2", "personality": "resistance_blue",
                    "connected": state["connected"], "free_heap": 100000}
        if cmd == "sounds":
            return {"sounds": [{"index": 0, "group": 1, "sound": 0, "ms": 1500}]}
        if cmd == "beep":
            if not state["connected"]:
                raise Fail("droid_unavailable", "cannot reach droid")
            if args.get("sound", 0) > 10:
                raise Fail("invalid_argument", "sound out of range")
            return {"ms": 1500, "turn_head": bool(args.get("turn_head"))}
        if cmd == "play":
            if not state["connected"]:
                raise Fail("droid_unavailable", "cannot reach droid")
            if not (0 <= args.get("group", -1) <= 255 and 0 <= args.get("sound", -1) <= 255):
                raise Fail("invalid_argument", "group/sound")
            return {}
        if cmd == "move":
            if not state["connected"]:
                raise Fail("droid_unavailable", "cannot reach droid")
            if not 1 <= args.get("ms", 0) <= 5000:
                raise Fail("invalid_argument", "ms")
            return {"ms": args["ms"]}
        if cmd == "stop":
            return {}
        if cmd == "connect":
            state["connected"] = True
            return {"connect_ms": 800}
        if cmd == "check":
            return {"available": state["connected"]}
        if cmd == "diagnose":
            return {"address": "F7:E6:74:95:E5:53", "advertising": True, "rssi": -80,
                    "connect_ok": True, "ping_ok": True, "ping_ms": 40, "future_field": 1}
        if cmd == "get_config":
            return {"alias": "r2t2"}
        raise Fail("unknown_command", cmd)

    return handle
