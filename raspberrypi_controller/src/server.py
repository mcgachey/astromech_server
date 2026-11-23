"""Master controller (Raspberry Pi) for the astromech ESP32 boards.

- Web UI on / (React + Mantine, built into ./static): configure, test and monitor every
  attached droid and beacon board.
- JSON API under /api (used by the UI).
- POST /droids/<id>/beep/<sound>[?turn_head] and POST /droids/<id>/demo: same as the legacy
  raspberrypi server. <id> is the droid's alias, device_id or MAC address (from droids.yml).
- POST /demo[?droid=<alias>]: makes a droid beep (default: the first droid in droids.yml
  with a device_id). It never moves the droid.

Firmware images pushed by the build machine (FIRMWARE_DIR) can be listed and flashed onto a
board from the UI (/api/firmware, /api/boards/<id>/firmware).

Boards are found by scanning the serial ports and identified by their `device_id`. Their
names, notes and logs are kept in the data directory (DATA_DIR, a host volume in Docker).
Listens on port 5050 (the same port as the legacy raspberrypi server, which it replaces).
"""
import asyncio
import logging
import os
import time

import yaml
from asgiref.wsgi import WsgiToAsgi
from flask import Flask, jsonify, request, send_from_directory
from hypercorn.asyncio import serve
from hypercorn.config import Config

import bluetooth
from firmware import FirmwareStore
from ha import HaError, HomeAssistant
from manager import ApiError, BoardManager
from store import Store

CONFIG_PATH = os.environ.get("CONTROLLER_CONFIG", "/config/droids.yml")
DATA_DIR = os.environ.get("DATA_DIR", "/data")
FIRMWARE_DIR = os.environ.get("FIRMWARE_DIR", "/firmware")  # filled by `make install` in esp32/
STATIC_DIR = os.environ.get("STATIC_DIR", os.path.join(os.path.dirname(__file__), "static"))
PORT = int(os.environ.get("PORT", "5050"))

log = logging.getLogger("controller")
app = Flask(__name__, static_folder=None)
asgi_app = WsgiToAsgi(app)

droids: dict = {}                 # alias -> droids.yml entry; only droids with a device_id
manager: BoardManager = None      # created in main()
ha: HomeAssistant = None          # created in main()


def load_droids(path: str) -> dict:
  """Droids from droids.yml that have a board (a `device_id`), by alias."""
  with open(path) as f:
    config = yaml.safe_load(f) or {}
  return {e["alias"]: e for e in config.get("droids", []) if e.get("device_id")}


@app.errorhandler(ApiError)
def api_error(e: ApiError):
  return jsonify({"error": e.code, "message": e.message}), e.status


def _body() -> dict:
  data = request.get_json(silent=True)
  return data if isinstance(data, dict) else {}


# ---- API ---------------------------------------------------------------------------------

@app.get("/api/boards")
async def list_boards():
  return jsonify(manager.list_boards())


@app.post("/api/boards/scan")
async def scan_boards():
  return jsonify(await manager.scan())


@app.get("/api/boards/<device_id>")
async def get_board(device_id):
  return jsonify(manager.describe(device_id))


@app.patch("/api/boards/<device_id>")
async def patch_board(device_id):
  return jsonify(manager.update_board(device_id, _body()))


@app.delete("/api/boards/<device_id>")
async def forget_board(device_id):
  await manager.forget(device_id)
  return jsonify({"ok": True})


@app.get("/api/boards/<device_id>/state")
async def board_state(device_id):
  return jsonify(await manager.state(device_id))


@app.put("/api/boards/<device_id>/config")
async def board_config(device_id):
  return jsonify(await manager.configure(device_id, _body()))


@app.post("/api/boards/<device_id>/commands/<cmd>")
async def board_command(device_id, cmd):
  return jsonify(await manager.command(device_id, cmd, _body()))


@app.get("/api/boards/<device_id>/logs")
async def board_logs(device_id):
  since = request.args.get("since", default=0, type=int)
  limit = request.args.get("limit", default=500, type=int)
  return jsonify(manager.get_logs(device_id, since, limit))


@app.delete("/api/boards/<device_id>/logs")
async def clear_board_logs(device_id):
  manager.clear_logs(device_id)
  return jsonify({"ok": True})


# ---- bluetooth --------------------------------------------------------------------------

@app.errorhandler(bluetooth.BluetoothError)
def bluetooth_error(e: bluetooth.BluetoothError):
  return jsonify({"error": e.code, "message": e.message}), e.status


@app.post("/api/bluetooth/scan")
async def scan_bluetooth():
  """Scan for BLE droids (takes `timeout` seconds, default 5). `all=true` lists every device."""
  body = _body()
  try:
    timeout = min(max(float(body.get("timeout", 5)), 1.0), 30.0)
  except (TypeError, ValueError):
    raise ApiError(400, "invalid_argument", "timeout must be a number of seconds")
  devices = await bluetooth.scan(timeout, include_all=body.get("all") is True)
  return jsonify({"devices": devices, "scanned_at": time.time()})


# ---- firmware ---------------------------------------------------------------------------

@app.get("/api/firmware")
async def list_firmware():
  role = request.args.get("role")
  return jsonify({"images": manager.firmware.list(role), "scanned_at": manager.firmware.scanned_at,
                  "boards": {b["device_id"]: b.get("info", {}).get("firmware_version")
                             for b in manager.list_boards() if b["online"]}})


@app.post("/api/firmware/scan")
async def scan_firmware():
  """Look for images newly pushed by `make install` (validates their checksums)."""
  images = await asyncio.to_thread(manager.firmware.scan)
  return jsonify({"images": images, "scanned_at": manager.firmware.scanned_at})


@app.get("/api/boards/<device_id>/firmware")
async def board_firmware(device_id):
  return jsonify(manager.board_firmware(device_id))


@app.post("/api/boards/<device_id>/firmware")
async def flash_board(device_id):
  """Flash the full image of `version` onto the board (in the background; poll GET)."""
  version = _body().get("version")
  if not isinstance(version, str) or not version:
    raise ApiError(400, "invalid_argument", "version is required")
  return jsonify(await manager.start_flash(device_id, version)), 202


@app.get("/api/openapi.json")
def openapi_spec():
  with open(os.path.join(os.path.dirname(__file__), "openapi.yaml")) as f:
    return jsonify(yaml.safe_load(f))


# ---- Home Assistant ----------------------------------------------------------------------

@app.errorhandler(HaError)
def ha_error(e: HaError):
  return jsonify({"error": e.code, "message": e.message}), 400


@app.get("/api/home_assistant")
async def get_ha():
  return jsonify(ha.public_settings())


@app.put("/api/home_assistant")
async def put_ha():
  return jsonify(ha.update_settings(_body()))


@app.post("/api/home_assistant/test")
async def test_ha():
  """Tests the posted (possibly unsaved) URL/token; blank fields fall back to the saved ones."""
  return jsonify({"ok": True, **await ha.test(_body())})


@app.post("/api/boards/<device_id>/home_assistant/send")
async def send_ha(device_id):
  return jsonify(await ha.send_now(device_id))


# ---- legacy /droids/<id> API (same paths and responses as raspberrypi/) --------------------

def _norm_mac(value: str) -> str:
  return str(value).strip().upper().replace("-", ":")


def resolve_droid(droid_id: str) -> dict:
  """The droids.yml entry whose alias, device_id or MAC address is `droid_id`."""
  for entry in droids.values():
    if droid_id == entry["alias"] or droid_id.lower() == str(entry["device_id"]).lower():
      return entry
    if entry.get("mac_address") and _norm_mac(droid_id) == _norm_mac(entry["mac_address"]):
      return entry
  raise ApiError(404, "unknown_droid", f"no droid {droid_id!r} (use its alias, device_id or MAC address)")


def _droid_board(droid_id: str) -> str:
  device_id = str(resolve_droid(droid_id)["device_id"])
  if device_id not in manager.registry:
    raise ApiError(503, "board_unavailable", "board not found yet")
  return device_id


@app.post("/droids/<droid_id>/beep/<int:sound_id>")
async def legacy_beep(droid_id, sound_id):
  device_id = _droid_board(droid_id)
  turn_head = "turn_head" in request.args
  result = await manager.command(device_id, "beep", {"sound": sound_id, "turn_head": turn_head})
  return jsonify({"ms": result["ms"], "turn_head": turn_head})


@app.post("/droids/<droid_id>/demo")
async def legacy_demo(droid_id):
  await manager.command(_droid_board(droid_id), "demo", {})
  return jsonify({})


# ---- demo (original endpoint) --------------------------------------------------------------

@app.post("/demo")
async def demo():
  alias = request.args.get("droid") or next(iter(droids), None)
  if alias not in droids:
    return jsonify({"error": "unknown_droid", "message": f"no droid {alias!r} with a device_id"}), 404
  device_id = str(droids[alias]["device_id"])
  if device_id not in manager.registry:
    return jsonify({"error": "board_unavailable", "message": "board not found yet"}), 503
  sound = int(droids[alias].get("demo_sound", 0))
  try:
    result = await manager.command(device_id, "beep", {"sound": sound, "wait": True})
  except ApiError as e:
    return jsonify({"error": e.code, "message": e.message}), e.status
  return jsonify({"ms": result["ms"], "sound": sound, "droid": alias})


# ---- web UI ----------------------------------------------------------------------------------

@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def ui(path):
  if path.startswith("api/"):
    return jsonify({"error": "not_found", "message": "no such endpoint"}), 404
  if path and os.path.isfile(os.path.join(STATIC_DIR, path)):
    return send_from_directory(STATIC_DIR, path)
  if os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
    return send_from_directory(STATIC_DIR, "index.html")
  return "UI not built (see raspberrypi_controller/README.md)", 404


async def main():
  global manager, ha
  store = Store(DATA_DIR)
  manager = BoardManager(store, {str(e["device_id"]): e for e in droids.values()},
                         FirmwareStore(FIRMWARE_DIR))
  ha = HomeAssistant(store, manager)
  manager.on_ha_change = ha.poke
  manager.ha_status = lambda device_id: ha.status.get(device_id)
  supervisor = asyncio.create_task(manager.supervise())
  updater = asyncio.create_task(ha.run())
  hconfig = Config()
  hconfig.bind = [f"0.0.0.0:{PORT}"]
  try:
    await serve(asgi_app, hconfig)
  finally:
    supervisor.cancel()
    updater.cancel()
    await manager.shutdown()


if __name__ == "__main__":
  logging.basicConfig(level=logging.INFO)
  droids = load_droids(CONFIG_PATH)
  asyncio.run(main())
