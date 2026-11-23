"""Keeps track of the attached ESP32 boards: discovery, connections, logs, commands."""
import asyncio
import dataclasses
import logging
import time
from collections import deque

from astromech_boards import (AstromechBoardsError, AsyncBeaconBoard, AsyncDroidBoard, BoardError,
                              BoardTimeout, DroidUnavailable, find_boards)
from astromech_boards.discovery import candidate_ports

import firmware as fw
from ha import valid_entity
from store import KEEP_ENTRIES, Store

log = logging.getLogger("controller.manager")

SCAN_INTERVAL = 20.0  # seconds between automatic scans while a known board is offline
RESTART_POLL = 2.0    # seconds between rescans while waiting for a freshly flashed board

_ASYNC_CLS = {"droid": AsyncDroidBoard, "beacon": AsyncBeaconBoard}

# Commands the UI may send. Wheel movement (move/stop) is deliberately absent.
DROID_COMMANDS = {"beep", "play", "volume", "center_head", "look_around", "demo", "connect", "disconnect",
                  "check", "diagnose"}
BEACON_COMMANDS = {"start", "stop"}
COMMON_COMMANDS = {"ping", "reboot", "factory_reset"}
# Drive the droid (per-motor power, head turns, wheel stop). Only accepted from local programs (loopback
# clients such as the robotics server on the same Pi), never from the browser UI on the network.
WHEEL_COMMANDS = {"motor", "rotate_head", "stop"}


class ApiError(Exception):
  def __init__(self, status: int, code: str, message: str):
    super().__init__(message)
    self.status, self.code, self.message = status, code, message


def _plain(value):
  if isinstance(value, list):
    return [_plain(v) for v in value]
  return dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value


class BoardManager:
  def __init__(self, store: Store, droid_defaults: dict = None, firmware: fw.FirmwareStore = None):
    self.store = store
    self.firmware = firmware
    self._flash: dict = {}                             # device_id -> latest flash status
    self._flash_tasks: dict = {}                       # device_id -> running flash task
    self._flash_ports: dict = {}                       # device_id -> port reserved for flashing
    self.registry: dict = store.load_boards()          # device_id -> record
    self.logs: dict = {}                               # device_id -> deque of entries
    self.seq: dict = {}                                # device_id -> last sequence number
    self._boards: dict = {}                            # device_id -> open async board
    self._unregister: dict = {}                        # device_id -> remove-listener function
    self._locks: dict = {}                             # device_id -> asyncio.Lock (open/close)
    self._scan_lock = None
    self.on_ha_change = None                           # called when a droid's HA settings change
    self.ha_status = lambda device_id: None            # set by main(): last HA update outcome
    self._loop = None
    self._last_error: dict = {}                        # device_id -> last connection problem
    # droids.yml entries (by device_id) give boards a first name.
    self._defaults = droid_defaults or {}
    for device_id in self.registry:
      self._load_log(device_id)

  # ---- logs ------------------------------------------------------------

  def _load_log(self, device_id: str):
    entries = self.store.load_log(device_id)
    self.logs[device_id] = entries
    self.seq[device_id] = entries[-1]["seq"] if entries else 0

  def add_log(self, device_id: str, kind: str, message: str, data=None, level: str = "info"):
    """Append to a board's log (memory + disk). Call on the event loop thread."""
    if device_id not in self.logs:
      self._load_log(device_id)
    self.seq[device_id] += 1
    entry = {"seq": self.seq[device_id], "ts": time.time(), "kind": kind, "level": level,
             "message": message}
    if data is not None:
      entry["data"] = data
    self.logs[device_id].append(entry)
    self.store.append_log(device_id, entry)

  def get_logs(self, device_id: str, since: int = 0, limit: int = KEEP_ENTRIES) -> dict:
    self._require(device_id)
    entries = [e for e in self.logs.get(device_id, ()) if e["seq"] > since]
    return {"entries": entries[-limit:], "last_seq": self.seq.get(device_id, 0)}

  def clear_logs(self, device_id: str):
    self._require(device_id)
    self.store.clear_log(device_id)
    self.logs[device_id] = deque(maxlen=KEEP_ENTRIES)  # sequence numbers keep increasing

  # ---- registry --------------------------------------------------------

  def _require(self, device_id: str) -> dict:
    rec = self.registry.get(device_id)
    if rec is None:
      raise ApiError(404, "unknown_board", f"no board {device_id!r}")
    return rec

  def _save(self):
    self.store.save_boards(self.registry)

  def _register(self, found) -> dict:
    """Add a board seen by a scan (or refresh what we know of it)."""
    info = found.info
    rec = self.registry.get(info.device_id)
    now = time.time()
    if rec is None:
      default = self._defaults.get(info.device_id, {})
      rec = self.registry[info.device_id] = {
          "device_id": info.device_id,
          "role": info.role,
          "name": default.get("alias") or f"{info.role}-{info.device_id[-4:]}",
          "notes": "",
          "demo_sound": int(default.get("demo_sound", 0)),
          "ha_entity": default.get("home_assistant_entity", ""),
          "ha_enabled": bool(default.get("home_assistant_entity")),
          "first_seen": now,
      }
      self.add_log(info.device_id, "system", f"board discovered on {found.port}")
    rec.update(role=info.role, port=found.port, last_seen=now)
    self._save()
    return rec

  def describe(self, device_id: str) -> dict:
    rec = self._require(device_id)
    board = self._boards.get(device_id)
    online = board is not None and not board.closed
    out = dict(rec)
    out["online"] = online
    out.setdefault("ha_entity", "")
    out.setdefault("ha_enabled", False)
    out["ha_status"] = self.ha_status(device_id)
    if online:
      out["info"] = dataclasses.asdict(board.info)
    if not online and device_id in self._last_error:
      out["error"] = self._last_error[device_id]
    if device_id in self._flash:
      out["flash"] = dict(self._flash[device_id])
    return out

  def list_boards(self) -> list:
    boards = [self.describe(d) for d in self.registry]
    return sorted(boards, key=lambda b: (b["role"], b["name"].lower()))

  def update_board(self, device_id: str, fields: dict) -> dict:
    rec = self._require(device_id)
    if "name" in fields:
      name = str(fields["name"]).strip()
      if not 1 <= len(name) <= 40:
        raise ApiError(400, "invalid_argument", "name must be 1-40 characters")
      rec["name"] = name
    if "notes" in fields:
      rec["notes"] = str(fields["notes"])[:2000]
    if "demo_sound" in fields:
      try:
        rec["demo_sound"] = max(0, int(fields["demo_sound"]))
      except (TypeError, ValueError):
        raise ApiError(400, "invalid_argument", "demo_sound must be a number") from None
    if "ha_entity" in fields:
      entity = str(fields["ha_entity"] or "").strip()
      if entity and not valid_entity(entity):
        raise ApiError(400, "invalid_argument", "entity must look like binary_sensor.r2_t2")
      rec["ha_entity"] = entity
    if "ha_enabled" in fields:
      rec["ha_enabled"] = bool(fields["ha_enabled"])
    if rec.get("ha_enabled") and not rec.get("ha_entity"):
      raise ApiError(400, "invalid_argument", "set an entity before enabling updates")
    self._save()
    if any(k.startswith("ha_") for k in fields) and self.on_ha_change:
      self.on_ha_change()
    return self.describe(device_id)

  async def forget(self, device_id: str):
    self._require(device_id)
    if self._flash.get(device_id, {}).get("active"):
      raise ApiError(409, "flash_in_progress", "the board is being flashed")
    await self._close(device_id)
    del self.registry[device_id]
    self._flash.pop(device_id, None)
    self.logs.pop(device_id, None)
    self.seq.pop(device_id, None)
    self._last_error.pop(device_id, None)
    self.store.delete_board_data(device_id)
    self._save()

  # ---- discovery and connections ---------------------------------------

  def _lock_for(self, device_id: str) -> asyncio.Lock:
    return self._locks.setdefault(device_id, asyncio.Lock())

  def _get_scan_lock(self) -> asyncio.Lock:
    if self._scan_lock is None:
      self._scan_lock = asyncio.Lock()
    return self._scan_lock

  async def scan(self) -> list:
    """Probe the serial ports we don't already hold open, and connect to what answers.

    Ports reserved for a flash are left alone: probing resets the board mid-write."""
    async with self._get_scan_lock():
      held = {b.port for b in self._boards.values() if not b.closed}
      held |= set(self._flash_ports.values())
      ports = [p for p in await asyncio.to_thread(candidate_ports) if p not in held]
      found = await asyncio.to_thread(find_boards, ports) if ports else []
      for f in found:
        if f.info.device_id in self._flash_ports:
          continue
        if f.info.device_id in self._boards and not self._boards[f.info.device_id].closed:
          continue
        self._register(f)
        try:
          await self._open(f.info.device_id, f.port, f.info.role)
        except AstromechBoardsError as e:
          self._last_error[f.info.device_id] = str(e)
          self.add_log(f.info.device_id, "system", f"could not open {f.port}: {e}", level="error")
      return self.list_boards()

  async def _open(self, device_id: str, port: str, role: str):
    async with self._lock_for(device_id):
      old = self._boards.get(device_id)
      if old is not None and not old.closed:
        return
      board = await _ASYNC_CLS[role].open(port)
      loop = asyncio.get_running_loop()
      self._loop = loop

      def on_event(e, device_id=device_id):  # runs on the SDK's reader thread
        loop.call_soon_threadsafe(self._on_event, device_id, e)

      self._unregister[device_id] = board.on_event(on_event)
      self._boards[device_id] = board
      self._last_error.pop(device_id, None)
      self.add_log(device_id, "system",
                   f"connected on {port} (firmware {board.info.firmware_version})")

  async def _close(self, device_id: str):
    async with self._lock_for(device_id):
      board = self._boards.pop(device_id, None)
      remove = self._unregister.pop(device_id, None)
      if remove:
        remove()
      if board is not None:
        try:
          await board.close()
        except Exception:
          pass

  def _on_event(self, device_id: str, e: dict):
    name = e.get("event", "?")
    data = e.get("data")
    if name == "log":
      self.add_log(device_id, "log", (data or {}).get("msg", ""), data)
    elif name == "disconnected":
      self.add_log(device_id, "event", "serial link lost: " + str((data or {}).get("error")),
                   data, level="error")
    else:
      self.add_log(device_id, "event", name + (f" {data}" if data else ""), data)

  async def _live(self, device_id: str):
    self._require(device_id)
    board = self._boards.get(device_id)
    if board is None or board.closed:
      raise ApiError(503, "board_unavailable", "the board is not connected")
    return board

  async def supervise(self):
    """Background task: notice lost boards and rescan while a known board is offline."""
    while True:
      try:
        for device_id, board in list(self._boards.items()):
          if board.closed:
            await self._close(device_id)
            self.add_log(device_id, "system", "board went offline", level="warning")
        if any(d not in self._boards for d in self.registry) or not self.registry:
          await self.scan()
      except Exception:
        log.exception("supervisor pass failed")
      await asyncio.sleep(SCAN_INTERVAL)

  async def shutdown(self):
    for task in list(self._flash_tasks.values()):
      task.cancel()
    await asyncio.gather(*self._flash_tasks.values(), return_exceptions=True)
    for device_id in list(self._boards):
      await self._close(device_id)

  # ---- firmware --------------------------------------------------------

  def board_firmware(self, device_id: str) -> dict:
    """What the board runs, the images it could be flashed with, and the latest flash status."""
    rec = self._require(device_id)
    board = self._boards.get(device_id)
    online = board is not None and not board.closed
    running = None
    if online:
      running = {"version": board.info.firmware_version, "build": board.info.build}
    return {"role": rec["role"], "running": running, "flash": self._flash.get(device_id),
            "images": self.firmware.list(rec["role"]) if self.firmware else []}

  async def start_flash(self, device_id: str, version: str) -> dict:
    """Begin flashing ``version`` (full image) in the background; poll describe()/board_firmware()."""
    rec = self._require(device_id)
    if self.firmware is None:
      raise ApiError(503, "firmware_unavailable", "no firmware directory is configured")
    role = rec["role"]
    # Re-check the files on disk right before writing them to a board.
    image = await asyncio.to_thread(self.firmware.reload, role, str(version))
    if image is None:
      other = self.firmware.find(str(version), exclude_role=role)
      if other:
        raise ApiError(409, "wrong_role", f"{version} is {other[0]['role']} firmware; "
                                         f"this is a {role} board")
      raise ApiError(404, "unknown_firmware", f"no {role} firmware {version}")
    if not image["valid"]:
      raise ApiError(400, "invalid_firmware", f"{role} {version}: {image['error']}")
    async with self._get_scan_lock():  # lets a scan that may be probing this port finish first
      if self._flash.get(device_id, {}).get("active"):  # includes the wait for the restart
        raise ApiError(409, "flash_in_progress", "the board is already being flashed")
      board = self._boards.get(device_id)
      port = board.port if board is not None and not board.closed else rec.get("port")
      if not port:
        raise ApiError(409, "no_port", "the serial port of this board is not known yet; scan first")
      if port in self._flash_ports.values():
        raise ApiError(409, "flash_in_progress", f"{port} is being flashed")
      self._flash_ports[device_id] = port
      self._flash[device_id] = {"version": image["version"], "stage": "starting", "active": True,
                                "percent": 0, "error": None, "started": time.time(),
                                "finished": None}
    task = asyncio.create_task(self._run_flash(device_id, port, image))
    self._flash_tasks[device_id] = task
    task.add_done_callback(lambda _t: self._flash_tasks.pop(device_id, None))  # when fully done
    return dict(self._flash[device_id])

  async def _run_flash(self, device_id: str, port: str, image: dict):
    st = self._flash[device_id]
    version = image["version"]
    self.add_log(device_id, "system", f"flashing {image['role']} firmware {version} "
                                      f"({image['build_id']}) to {port}")
    error = None
    try:
      st["stage"] = "releasing port"
      await self._close(device_id)
      st["stage"] = "writing"

      def on_output(line: str, percent):
        if percent is not None:
          st["percent"] = percent
        else:
          self.add_log(device_id, "system", f"esptool: {line}")

      await fw.flash(port, image, on_output)
      st["percent"] = 100
    except fw.FlashError as e:
      error = f"{e}. If the board never entered the bootloader, hold BOOT while pressing EN and retry."
    except asyncio.CancelledError:
      error = "cancelled (the controller is shutting down)"
      raise
    except Exception as e:
      log.exception("flash of %s failed", device_id)
      error = f"unexpected error: {e}"
    finally:
      self._flash_ports.pop(device_id, None)  # scanning may resume
      if error:
        st.update(stage="failed", active=False, error=error, finished=time.time())
        self.add_log(device_id, "error", f"flash failed: {error}", level="error")
    if error:
      return
    st["stage"] = "restarting"
    self.add_log(device_id, "system", "flash written; waiting for the board to restart")
    running = await self._await_board(device_id)
    if running == version:
      st.update(stage="done", active=False, finished=time.time())
      self.add_log(device_id, "system", f"flash complete: now running {version}")
      return
    error = (f"the board reports firmware {running} instead of {version}" if running else
             "the board did not answer after the flash; press EN, then scan for boards")
    st.update(stage="failed", active=False, error=error, finished=time.time())
    self.add_log(device_id, "error", f"flash failed: {error}", level="error")

  async def _await_board(self, device_id: str):
    """Rescan until the board answers again; returns its firmware version (None if it never does)."""
    for _ in range(6):
      await asyncio.sleep(RESTART_POLL)
      try:
        await self.scan()
      except Exception:
        log.exception("scan after flash failed")
      board = self._boards.get(device_id)
      if board is not None and not board.closed:
        return board.info.firmware_version
    return None

  # ---- talking to a board ----------------------------------------------

  async def _call(self, device_id: str, label: str, fn, args=None, quiet=False):
    """Run a board call, logging the request and its outcome (unless ``quiet``: polling)."""
    board = await self._live(device_id)
    if not quiet:
      self.add_log(device_id, "command", label, args or None)
    t0 = time.monotonic()
    try:
      result = _plain(await fn(board))
    except DroidUnavailable as e:
      self.add_log(device_id, "error", f"{label}: {e.message}", level="warning")
      raise ApiError(503, "droid_unavailable", e.message) from e
    except BoardError as e:
      self.add_log(device_id, "error", f"{label}: {e}", level="warning")
      raise ApiError(400, e.code, e.message) from e
    except BoardTimeout as e:
      self.add_log(device_id, "error", f"{label}: {e}", level="error")
      await self._close(device_id)  # reopened by the next scan
      raise ApiError(504, "timeout", str(e)) from e
    except AstromechBoardsError as e:
      self.add_log(device_id, "error", f"{label}: {e}", level="error")
      await self._close(device_id)
      raise ApiError(503, "board_unavailable", str(e)) from e
    ms = int((time.monotonic() - t0) * 1000)
    if quiet:
      return result if isinstance(result, dict) else {"result": result}
    self.add_log(device_id, "response", f"{label} ok ({ms} ms)", result if result else None)
    return result if isinstance(result, dict) else {"result": result}

  async def state(self, device_id: str) -> dict:
    """Live status and saved config (plus the sound bank for droids)."""
    rec = self._require(device_id)
    status = await self._call(device_id, "status", lambda b: b.status(), quiet=True)
    config = await self._call(device_id, "get_config", lambda b: b.get_config(), quiet=True)
    out = {"status": status, "config": config}
    if rec["role"] == "droid" and status.get("configured"):
      try:
        out["sounds"] = (await self._call(device_id, "sounds", lambda b: b.sounds(), quiet=True)).get("result", [])
      except ApiError:
        out["sounds"] = []
    return out

  async def configure(self, device_id: str, body: dict) -> dict:
    rec = self._require(device_id)
    if rec["role"] == "droid":
      fields = {k: body[k] for k in ("alias", "address", "type", "personality") if body.get(k)}
      if not fields:
        raise ApiError(400, "invalid_argument", "nothing to change")
      restart = bool(body.get("reboot", True))
      return await self._call(device_id, "set_config", lambda b: b.configure(restart=restart, **fields),
                              {**fields, "reboot": restart})
    kind = body.get("kind", "silent")
    if kind not in ("silent", "location"):
      raise ApiError(400, "invalid_argument", "kind must be silent or location")
    location_id = body.get("location_id")
    if kind == "location":
      try:
        location_id = int(location_id)
      except (TypeError, ValueError):
        raise ApiError(400, "invalid_argument", "location_id (0-255) is required") from None
      if not 0 <= location_id <= 255:
        raise ApiError(400, "invalid_argument", "location_id must be 0-255")
    persist = bool(body.get("persist", True))
    return await self._call(
        device_id, "set_beacon",
        lambda b: b.set_beacon(kind, location_id=location_id, persist=persist),
        {"kind": kind, "location_id": location_id, "persist": persist})

  async def command(self, device_id: str, cmd: str, args: dict, local: bool = False) -> dict:
    rec = self._require(device_id)
    allowed = COMMON_COMMANDS | (DROID_COMMANDS if rec["role"] == "droid" else BEACON_COMMANDS)
    if rec["role"] == "droid" and cmd in WHEEL_COMMANDS:
      if not local:
        raise ApiError(403, "local_only", f"{cmd!r} is only accepted from programs on the controller itself")
      allowed = allowed | WHEEL_COMMANDS
    if cmd not in allowed:
      raise ApiError(400, "unknown_command", f"{cmd!r} is not available for a {rec['role']} board")

    def num(key, lo, hi, default=None):
      v = args.get(key, default)
      try:
        v = int(v)
      except (TypeError, ValueError):
        raise ApiError(400, "invalid_argument", f"{key} must be a number") from None
      if not lo <= v <= hi:
        raise ApiError(400, "invalid_argument", f"{key} must be {lo}-{hi}")
      return v

    if cmd == "beep":
      sound = num("sound", 0, 10000, rec.get("demo_sound", 0))
      head, wait = bool(args.get("turn_head")), bool(args.get("wait"))
      return await self._call(device_id, f"beep {sound}",
                              lambda b: b.beep(sound, turn_head=head, wait=wait),
                              {"sound": sound, "turn_head": head, "wait": wait})
    if cmd == "play":
      group, sound = num("group", 0, 255), num("sound", 0, 255)
      return await self._call(device_id, f"play {group}:{sound}", lambda b: b.play(group, sound),
                              {"group": group, "sound": sound})
    if cmd == "volume":
      level = num("level", 0, 31)
      return await self._call(device_id, f"volume {level}", lambda b: b.set_volume(level),
                              {"level": level})
    if cmd == "motor":
      motor = args.get("motor")
      if motor not in ("left", "right"):
        raise ApiError(400, "invalid_argument", "motor must be left or right")
      speed = num("speed", 0, 255)
      ramp = num("ramp_ms", 0, 65535) if args.get("ramp_ms") is not None else None
      backward = bool(args.get("backward"))
      return await self._call(device_id, f"motor {motor} {'-' if backward else '+'}{speed}",
                              lambda b: b.motor(motor, speed, backward=backward, ramp_ms=ramp),
                              {"motor": motor, "speed": speed, "backward": backward, "ramp_ms": ramp})
    if cmd == "rotate_head":
      direction = args.get("direction")
      if direction not in ("left", "right"):
        raise ApiError(400, "invalid_argument", "direction must be left or right")
      return await self._call(device_id, f"rotate_head {direction}", lambda b: b.rotate_head(direction),
                              {"direction": direction})
    simple = {
        "center_head": lambda b: b.center_head(), "look_around": lambda b: b.look_around(),
        "demo": lambda b: b.demo(), "connect": lambda b: b.connect(),
        "disconnect": lambda b: b.disconnect(), "check": lambda b: b.check_alive(),
        "diagnose": lambda b: b.diagnose(), "ping": lambda b: b.ping(),
        "reboot": lambda b: b.reboot(), "factory_reset": lambda b: b.factory_reset(),
        "start": lambda b: b.start(), "stop": lambda b: b.stop(),  # beacon start/stop; droid wheel stop
    }
    return await self._call(device_id, cmd, simple[cmd])
