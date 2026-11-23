import asyncio
import tempfile
import unittest

import helpers  # noqa: F401  (puts src/ on the path)
from manager import ApiError, BoardManager
from store import Store

DEVICE = "f481850ee93c"


class FakeDroid:
  closed = False

  def __init__(self):
    self.calls = []

  async def motor(self, *a, **kw):
    self.calls.append(("motor", a, kw))
    return None

  async def rotate_head(self, *a, **kw):
    self.calls.append(("rotate_head", a, kw))
    return None

  async def stop(self):
    self.calls.append(("stop",))
    return None


def run(coro):
  return asyncio.run(coro)


class WheelCommandTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.m = BoardManager(Store(self.tmp.name))
    self.m.registry[DEVICE] = {"device_id": DEVICE, "role": "droid", "name": "d"}
    self.droid = FakeDroid()
    self.m._boards[DEVICE] = self.droid

  def test_refused_from_the_network(self):
    for cmd, args in (("motor", {"motor": "left", "speed": 5}), ("rotate_head", {"direction": "left"}), ("stop", {})):
      with self.assertRaises(ApiError) as cm:
        run(self.m.command(DEVICE, cmd, args))
      self.assertEqual((cm.exception.status, cm.exception.code), (403, "local_only"))
    self.assertEqual(self.droid.calls, [])

  def test_motor_from_local(self):
    run(self.m.command(DEVICE, "motor", {"motor": "right", "speed": 128, "backward": True, "ramp_ms": 100}, local=True))
    run(self.m.command(DEVICE, "motor", {"motor": "left", "speed": 0}, local=True))
    self.assertEqual(self.droid.calls, [("motor", ("right", 128), {"backward": True, "ramp_ms": 100}),
                                         ("motor", ("left", 0), {"backward": False, "ramp_ms": None})])

  def test_validation(self):
    for args in ({"motor": "head", "speed": 5}, {"motor": "left", "speed": 300}, {"motor": "left"},
                 {"motor": "left", "speed": 5, "ramp_ms": 70000}):
      with self.assertRaises(ApiError) as cm:
        run(self.m.command(DEVICE, "motor", args, local=True))
      self.assertEqual(cm.exception.status, 400)
    with self.assertRaises(ApiError):
      run(self.m.command(DEVICE, "rotate_head", {"direction": "up"}, local=True))
    self.assertEqual(self.droid.calls, [])

  def test_rotate_head_and_stop(self):
    run(self.m.command(DEVICE, "rotate_head", {"direction": "right"}, local=True))
    run(self.m.command(DEVICE, "stop", {}, local=True))
    self.assertEqual(self.droid.calls, [("rotate_head", ("right",), {}), ("stop",)])

  def test_beacon_cannot_drive(self):
    self.m.registry[DEVICE]["role"] = "beacon"
    with self.assertRaises(ApiError) as cm:
      run(self.m.command(DEVICE, "motor", {"motor": "left", "speed": 5}, local=True))
    self.assertEqual(cm.exception.code, "unknown_command")


if __name__ == "__main__":
  unittest.main()
