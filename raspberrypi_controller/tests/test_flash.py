import asyncio
import json
import os
import tempfile
import unittest
from unittest import mock

import helpers
import manager as manager_mod
from astromech_boards.models import BoardInfo
from firmware import FirmwareStore
from manager import ApiError, BoardManager
from store import Store

DEVICE = "f481850ee93c"
PORT = "/dev/ttyUSB0"


class FakeBoard:
  def __init__(self, version, port=PORT, on_close=None):
    self.port, self.closed = port, False
    self.info = BoardInfo(role="droid", firmware_version=version, protocol=1, device_id=DEVICE,
                          uptime_ms=0, build="x")
    self._on_close = on_close

  async def close(self):
    self.closed = True
    if self._on_close:
      self._on_close()


class FlashTest(unittest.IsolatedAsyncioTestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.fwdir = os.path.join(self.tmp.name, "fw")
    helpers.make_image(self.fwdir, "droid", "0.2.0")
    helpers.make_image(self.fwdir, "droid", "0.3.0")
    helpers.make_image(self.fwdir, "beacon", "0.3.0")
    self.m = BoardManager(Store(os.path.join(self.tmp.name, "data")), {}, FirmwareStore(self.fwdir))
    self.m.registry[DEVICE] = {"device_id": DEVICE, "role": "droid", "name": "r2", "port": PORT}
    self.events = []
    self.m._boards[DEVICE] = FakeBoard("0.2.0", on_close=lambda: self.events.append("closed"))
    patch = mock.patch.object(manager_mod, "RESTART_POLL", 0.01)
    patch.start()
    self.addCleanup(patch.stop)
    self.addCleanup(self.tmp.cleanup)

  def use_esptool(self, **kw):
    path = helpers.fake_esptool(self.tmp.name, **kw)
    patch = mock.patch.dict(os.environ, {"ESPTOOL_CMD": path})
    patch.start()
    self.addCleanup(patch.stop)

  def comes_back_as(self, version):
    """Make the post-flash rescan reconnect the board running ``version``."""
    async def scan():
      self.events.append("scan")
      self.m._boards[DEVICE] = FakeBoard(version)
      return []
    self.m.scan = scan

  async def finish(self):
    task = self.m._flash_tasks.get(DEVICE)
    if task:
      await asyncio.wait_for(task, 20)
    return self.m.describe(DEVICE)["flash"]

  async def test_success(self):
    self.use_esptool()
    self.comes_back_as("0.3.0")
    status = await self.m.start_flash(DEVICE, "0.3.0")
    self.assertTrue(status["active"])
    self.assertEqual(self.m._flash_ports[DEVICE], PORT)
    flash = await self.finish()
    self.assertEqual((flash["stage"], flash["active"], flash["error"]), ("done", False, None))
    self.assertEqual(flash["percent"], 100)
    self.assertEqual(self.events, ["closed", "scan"])  # port released before the rescan
    self.assertEqual(self.m._flash_ports, {})
    with open(os.path.join(self.tmp.name, "argv.json")) as f:
      argv = json.load(f)
    self.assertEqual(argv[argv.index("--port") + 1], PORT)
    self.assertEqual(argv[argv.index("write-flash") + 7::2], ["0x1000", "0x8000", "0xe000", "0x10000"])
    messages = [e["message"] for e in self.m.logs[DEVICE]]
    self.assertTrue(any("flash complete" in x for x in messages))
    self.assertFalse(any("Writing at" in x for x in messages))  # progress is not logged line by line

  async def test_esptool_failure_keeps_board_offline_and_reports(self):
    self.use_esptool(exit_code=2)
    self.comes_back_as("0.3.0")
    await self.m.start_flash(DEVICE, "0.3.0")
    flash = await self.finish()
    self.assertEqual((flash["stage"], flash["active"]), ("failed", False))
    self.assertIn("status 2", flash["error"])
    self.assertIn("BOOT", flash["error"])
    self.assertEqual(self.m._flash_ports, {})
    self.assertNotIn("scan", self.events)
    self.assertFalse(self.m.describe(DEVICE)["online"])

  async def test_wrong_version_after_flash_is_a_failure(self):
    self.use_esptool()
    self.comes_back_as("0.2.0")
    await self.m.start_flash(DEVICE, "0.3.0")
    flash = await self.finish()
    self.assertEqual(flash["stage"], "failed")
    self.assertIn("0.2.0", flash["error"])

  async def test_board_never_returns(self):
    self.use_esptool()

    async def scan():
      return []
    self.m.scan = scan
    await self.m.start_flash(DEVICE, "0.3.0")
    flash = await self.finish()
    self.assertEqual(flash["stage"], "failed")
    self.assertIn("did not answer", flash["error"])

  async def test_rejections(self):
    self.use_esptool()
    with self.assertRaises(ApiError) as e:
      await self.m.start_flash(DEVICE, "9.9.9")
    self.assertEqual((e.exception.status, e.exception.code), (404, "unknown_firmware"))
    with self.assertRaises(ApiError) as e:
      await self.m.start_flash("nope", "0.3.0")
    self.assertEqual(e.exception.status, 404)
    self.m.registry["bb"] = {"device_id": "bb", "role": "beacon", "name": "b", "port": "/dev/ttyUSB1"}
    # A droid-only version must never be offered to a beacon.
    helpers.make_image(self.fwdir, "droid", "0.4.0")
    self.m.firmware.scan()
    with self.assertRaises(ApiError) as e:
      await self.m.start_flash("bb", "0.4.0")
    self.assertEqual((e.exception.status, e.exception.code), (409, "wrong_role"))
    self.assertEqual(self.m._flash, {})
    # A corrupted image is refused, even if it was valid at the last scan.
    with open(os.path.join(self.fwdir, "droid", "0.3.0", "firmware.bin"), "ab") as f:
      f.write(b"x")
    with self.assertRaises(ApiError) as e:
      await self.m.start_flash(DEVICE, "0.3.0")
    self.assertEqual((e.exception.status, e.exception.code), (400, "invalid_firmware"))
    self.assertTrue(self.m._boards[DEVICE] and not self.m._boards[DEVICE].closed)  # untouched

  async def test_no_port_and_double_start(self):
    self.use_esptool()
    self.comes_back_as("0.3.0")
    del self.m._boards[DEVICE]
    del self.m.registry[DEVICE]["port"]
    with self.assertRaises(ApiError) as e:
      await self.m.start_flash(DEVICE, "0.3.0")
    self.assertEqual(e.exception.code, "no_port")
    self.m.registry[DEVICE]["port"] = PORT  # an offline board is flashed on its last known port
    await self.m.start_flash(DEVICE, "0.3.0")
    with self.assertRaises(ApiError) as e:
      await self.m.start_flash(DEVICE, "0.2.0")
    self.assertEqual((e.exception.status, e.exception.code), (409, "flash_in_progress"))
    with self.assertRaises(ApiError) as e:
      await self.m.forget(DEVICE)
    self.assertEqual(e.exception.code, "flash_in_progress")
    self.assertEqual((await self.finish())["stage"], "done")

  async def test_second_flash_refused_while_waiting_for_restart(self):
    self.use_esptool()
    gate = asyncio.Event()

    async def scan():  # the board stays away until we let it back
      await gate.wait()
      self.m._boards[DEVICE] = FakeBoard("0.3.0")
      return []
    self.m.scan = scan
    await self.m.start_flash(DEVICE, "0.3.0")
    for _ in range(500):  # esptool is done once the port reservation is released
      if DEVICE not in self.m._flash_ports and self.m._flash[DEVICE]["stage"] == "restarting":
        break
      await asyncio.sleep(0.01)
    self.assertEqual(self.m._flash[DEVICE]["stage"], "restarting")
    for call in (lambda: self.m.start_flash(DEVICE, "0.2.0"), lambda: self.m.forget(DEVICE)):
      with self.assertRaises(ApiError) as e:
        await call()
      self.assertEqual((e.exception.status, e.exception.code), (409, "flash_in_progress"))
    gate.set()
    self.assertEqual((await self.finish())["stage"], "done")

  async def test_scan_leaves_the_flashing_port_alone(self):
    self.use_esptool()
    self.comes_back_as("0.3.0")
    real_scan = BoardManager.scan.__get__(self.m)
    probed = []

    def find(ports):
      probed.extend(ports)
      return []
    with mock.patch.object(manager_mod, "candidate_ports", lambda: [PORT, "/dev/ttyUSB1"]), \
         mock.patch.object(manager_mod, "find_boards", find):
      await self.m.start_flash(DEVICE, "0.3.0")
      await real_scan()
      self.assertEqual(probed, ["/dev/ttyUSB1"])
      await self.finish()
      probed.clear()
      self.m._boards.clear()
      await real_scan()
      self.assertEqual(probed, [PORT, "/dev/ttyUSB1"])  # probed again once the flash is over

  async def test_board_firmware_view(self):
    view = self.m.board_firmware(DEVICE)
    self.assertEqual(view["running"]["version"], "0.2.0")
    self.assertEqual([i["version"] for i in view["images"]], ["0.3.0", "0.2.0"])  # droid only
    self.assertTrue(all(i["role"] == "droid" for i in view["images"]))
    self.assertIsNone(view["flash"])


if __name__ == "__main__":
  unittest.main()
