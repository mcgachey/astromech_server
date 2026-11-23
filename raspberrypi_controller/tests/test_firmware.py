import json
import os
import tempfile
import unittest

import helpers
from firmware import FirmwareStore, version_key


class FirmwareStoreTest(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.root = self.tmp.name

  def tearDown(self):
    self.tmp.cleanup()

  def image(self, role, version):
    return next(i for i in FirmwareStore(self.root).list() if i["role"] == role and i["version"] == version)

  def test_valid_image(self):
    helpers.make_image(self.root)
    img = self.image("droid", "0.2.0")
    self.assertTrue(img["valid"], img["error"])
    self.assertEqual(img["build_id"], "abc1234")
    self.assertEqual([f["offset"] for f in img["files"]], ["0x1000", "0x8000", "0xe000", "0x10000"])
    self.assertNotIn("path", img["files"][0])  # server paths are not exposed
    self.assertNotIn("dir", img)

  def test_sorted_newest_first_numerically(self):
    for v in ("0.2.0", "0.10.0", "0.9.1"):
      helpers.make_image(self.root, "droid", v)
    helpers.make_image(self.root, "beacon", "1.0.0")
    store = FirmwareStore(self.root)
    self.assertEqual([i["version"] for i in store.list("droid")], ["0.10.0", "0.9.1", "0.2.0"])
    self.assertEqual([i["role"] for i in store.list()], ["droid"] * 3 + ["beacon"])
    self.assertLess(version_key("0.9.1"), version_key("0.10.0"))

  def test_corrupt_file_is_invalid(self):
    d = helpers.make_image(self.root)
    with open(os.path.join(d, "firmware.bin"), "ab") as f:
      f.write(b"x")
    img = self.image("droid", "0.2.0")
    self.assertFalse(img["valid"])
    self.assertIn("sha256", img["error"])

  def test_missing_file_is_invalid(self):
    d = helpers.make_image(self.root)
    os.remove(os.path.join(d, "boot_app0.bin"))
    self.assertIn("missing", self.image("droid", "0.2.0")["error"])

  def test_wrong_role_in_manifest(self):
    helpers.make_image(self.root, "droid", "0.2.0", {"role": "beacon"})
    self.assertIn("manifest says", self.image("droid", "0.2.0")["error"])

  def test_wrong_chip(self):
    helpers.make_image(self.root, overrides={"chip": "esp32s3"})
    self.assertIn("chip", self.image("droid", "0.2.0")["error"])

  def test_path_traversal_rejected(self):
    helpers.make_image(self.root, overrides={"files": [
        {"name": "../../etc/passwd", "offset": "0x0", "sha256": "0"}]})
    self.assertIn("bad file name", self.image("droid", "0.2.0")["error"])

  def test_no_manifest_and_bad_json(self):
    os.makedirs(os.path.join(self.root, "droid", "0.1.0"))
    d = helpers.make_image(self.root, "droid", "0.3.0")
    with open(os.path.join(d, "manifest.json"), "w") as f:
      f.write("{nope")
    store = FirmwareStore(self.root)
    self.assertFalse(store.list()[-1]["valid"])
    self.assertEqual(len(store.list()), 2)

  def test_ignores_junk_dirs(self):
    os.makedirs(os.path.join(self.root, "droid", "latest"))
    os.makedirs(os.path.join(self.root, "other", "1.0.0"))
    self.assertEqual(FirmwareStore(self.root).list(), [])

  def test_scan_finds_new_and_reload_revalidates(self):
    store = FirmwareStore(self.root)
    self.assertEqual(store.list(), [])
    d = helpers.make_image(self.root)
    self.assertEqual(len(store.scan()), 1)
    with open(os.path.join(d, "firmware.bin"), "ab") as f:
      f.write(b"x")
    self.assertTrue(store.get("droid", "0.2.0")["valid"])  # stale until re-read
    self.assertFalse(store.reload("droid", "0.2.0")["valid"])
    self.assertIsNone(store.reload("droid", "9.9.9"))
    self.assertIsNone(store.reload("droid", "../../x"))

  def test_flash_argv(self):
    import firmware
    helpers.make_image(self.root)
    img = FirmwareStore(self.root).get("droid", "0.2.0")
    os.environ["ESPTOOL_CMD"] = "esptool"
    try:
      argv = firmware.flash_argv("/dev/ttyUSB0", img)
    finally:
      del os.environ["ESPTOOL_CMD"]
    self.assertEqual(argv[:6], ["esptool", "--chip", "esp32", "--port", "/dev/ttyUSB0", "--baud"])
    i = argv.index("write-flash")
    self.assertEqual(argv[i + 1:i + 7], ["--flash-mode", "dio", "--flash-freq", "40m",
                                         "--flash-size", "4MB"])
    pairs = argv[i + 7:]
    self.assertEqual(pairs[0::2], ["0x1000", "0x8000", "0xe000", "0x10000"])
    self.assertTrue(pairs[7].endswith("firmware.bin"))


if __name__ == "__main__":
  unittest.main()
