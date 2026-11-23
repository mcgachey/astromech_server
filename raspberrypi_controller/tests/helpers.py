"""Shared test helpers: fake firmware trees and a fake esptool."""
import hashlib
import json
import os
import stat
import sys
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

FILES = [("bootloader.bin", "0x1000"), ("partitions.bin", "0x8000"),
         ("boot_app0.bin", "0xe000"), ("firmware.bin", "0x10000")]


def make_image(root, role="droid", version="0.2.0", overrides=None):
  """Write a valid image under root/<role>/<version>; returns its directory."""
  d = os.path.join(root, role, version)
  os.makedirs(d, exist_ok=True)
  files = []
  for name, offset in FILES:
    data = f"{role}-{version}-{name}".encode() * 10
    with open(os.path.join(d, name), "wb") as f:
      f.write(data)
    files.append({"name": name, "offset": offset, "size": len(data),
                  "sha256": hashlib.sha256(data).hexdigest()})
  manifest = {"manifest_version": 1, "role": role, "version": version, "build_id": "abc1234",
              "chip": "esp32", "flash_mode": "dio", "flash_freq": "40m", "flash_size": "4MB",
              "created": "2026-01-01T00:00:00+00:00", "files": files}
  manifest.update(overrides or {})
  with open(os.path.join(d, "manifest.json"), "w") as f:
    json.dump(manifest, f)
  return d


def fake_esptool(directory, exit_code=0, progress=True, record="argv.json"):
  """An executable that records its argv, prints esptool-style output and exits."""
  path = os.path.join(directory, "fake_esptool")
  script = textwrap.dedent(f"""\
      #!{sys.executable}
      import json, sys
      json.dump(sys.argv[1:], open({os.path.join(directory, record)!r}, "w"))
      print("esptool v5.6.0")
      print("Connecting....")
      if {progress!r}:
        for pct in (10, 55, 100):
          sys.stdout.write(f"Writing at 0x00010000 [=====>   ] {{pct}}.0% 100/1000 bytes...\\r")
          sys.stdout.flush()
      if {exit_code}:
        print("A fatal error occurred: Failed to connect to ESP32")
      else:
        print("Hash of data verified.")
      sys.exit({exit_code})
      """)
  with open(path, "w") as f:
    f.write(script)
  os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
  return path
