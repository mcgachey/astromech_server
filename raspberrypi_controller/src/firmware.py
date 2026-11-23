"""Firmware images pushed by the build machine (`make install` in esp32/), and flashing them.

Layout of the firmware directory (FIRMWARE_DIR, mounted read-only at /firmware):

    <role>/<version>/manifest.json + the image files it lists

`manifest.json` is written by esp32/scripts/package.py: role, version, build_id, chip, flash
parameters and, per file, its name, flash offset and sha256. Nothing is flashed that fails
validation here.
"""
import asyncio
import hashlib
import json
import os
import re
import shlex
import sys
import time
from typing import Callable, Optional

ROLES = ("droid", "beacon")
CHIP = "esp32"
FLASH_BAUD = 460800
FLASH_TIMEOUT = 240.0  # seconds for the whole esptool run

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_OFFSET = re.compile(r"^0x[0-9a-fA-F]+$")
_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


class FlashError(Exception):
  pass


def version_key(version: str) -> tuple:
  try:
    return tuple(int(p) for p in version.split("."))
  except ValueError:
    return (-1,)


def _sha256(path: str) -> str:
  h = hashlib.sha256()
  with open(path, "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
      h.update(chunk)
  return h.hexdigest()


def _load_image(role: str, version: str, directory: str) -> dict:
  """One image entry; ``valid`` is False (with ``error``) if anything about it is wrong."""
  entry = {"role": role, "version": version, "build_id": "", "created": "", "size": 0,
           "valid": False, "error": "", "files": [], "chip": CHIP, "flash_mode": "dio",
           "flash_freq": "40m", "flash_size": "4MB", "dir": directory}
  try:
    with open(os.path.join(directory, "manifest.json")) as f:
      m = json.load(f)
    if m.get("role") != role or m.get("version") != version:
      raise ValueError(f"manifest says {m.get('role')} {m.get('version')}, "
                       f"but it is in {role}/{version}")
    if m.get("chip") != CHIP:
      raise ValueError(f"unsupported chip {m.get('chip')!r}")
    entry.update(build_id=str(m.get("build_id", "")), created=str(m.get("created", "")))
    for key in ("flash_mode", "flash_freq", "flash_size"):
      if not isinstance(m.get(key), str) or not _NAME.match(m[key]):
        raise ValueError(f"bad {key}")
      entry[key] = m[key]
    files = m.get("files")
    if not isinstance(files, list) or not files:
      raise ValueError("no files listed")
    seen = set()
    for f in files:
      name, offset = f.get("name"), f.get("offset")
      if not isinstance(name, str) or not _NAME.match(name) or name.startswith("."):
        raise ValueError(f"bad file name {name!r}")
      if not isinstance(offset, str) or not _OFFSET.match(offset):
        raise ValueError(f"{name}: bad offset {offset!r}")
      if offset in seen:
        raise ValueError(f"{name}: duplicate offset {offset}")
      seen.add(offset)
      path = os.path.join(directory, name)
      if not os.path.isfile(path):
        raise ValueError(f"{name} is missing")
      if _sha256(path) != f.get("sha256"):
        raise ValueError(f"{name}: sha256 mismatch")
      size = os.path.getsize(path)
      entry["size"] += size
      entry["files"].append({"name": name, "offset": offset, "size": size, "path": path})
    if not any(f["name"] == "firmware.bin" for f in entry["files"]):
      raise ValueError("firmware.bin is not listed")
    entry["valid"] = True
  except (OSError, ValueError, TypeError, AttributeError) as e:
    entry["error"] = str(e) if not isinstance(e, json.JSONDecodeError) else f"manifest.json: {e}"
  return entry


class FirmwareStore:
  def __init__(self, root: str):
    self.root = root
    self._images: list = []
    self.scanned_at: Optional[float] = None
    self.scan()

  def scan(self) -> list:
    """Re-read the firmware directory. Blocking (hashes files): run it in a thread."""
    images = []
    for role in ROLES:
      base = os.path.join(self.root, role)
      try:
        versions = [v for v in os.listdir(base) if os.path.isdir(os.path.join(base, v))]
      except OSError:
        continue
      for version in versions:
        if _SEMVER.match(version):
          images.append(_load_image(role, version, os.path.join(base, version)))
    images.sort(key=lambda i: (ROLES.index(i["role"]), tuple(-n for n in version_key(i["version"]))))
    self._images = images
    self.scanned_at = time.time()
    return self.list()

  def list(self, role: Optional[str] = None) -> list:
    """Public view of the images (no paths), newest first."""
    return [{k: v for k, v in i.items() if k not in ("dir", "files")} | {
        "files": [{k: v for k, v in f.items() if k != "path"} for f in i["files"]]}
        for i in self._images if role is None or i["role"] == role]

  def get(self, role: str, version: str) -> Optional[dict]:
    """The full internal entry (with file paths), or None."""
    return next((i for i in self._images if i["role"] == role and i["version"] == version), None)

  def find(self, version: str, exclude_role: Optional[str] = None) -> list:
    return [i for i in self.list() if i["version"] == version and i["role"] != exclude_role]

  def reload(self, role: str, version: str) -> Optional[dict]:
    """Re-validate one image from disk (blocking) and return it, or None if it is gone."""
    if role not in ROLES or not _SEMVER.match(version):
      return None
    directory = os.path.join(self.root, role, version)
    old = self.get(role, version)
    if not os.path.isdir(directory):
      if old is not None:
        self._images.remove(old)
      return None
    fresh = _load_image(role, version, directory)
    if old is not None:
      self._images[self._images.index(old)] = fresh
    else:
      self._images.append(fresh)
    return fresh


def esptool_command() -> list:
  override = os.environ.get("ESPTOOL_CMD")
  return shlex.split(override) if override else [sys.executable, "-m", "esptool"]


def flash_argv(port: str, image: dict) -> list:
  argv = esptool_command() + [
      "--chip", image["chip"], "--port", port, "--baud", str(FLASH_BAUD),
      "--before", "default-reset", "--after", "hard-reset",
      "write-flash", "--flash-mode", image["flash_mode"], "--flash-freq", image["flash_freq"],
      "--flash-size", image["flash_size"]]
  for f in sorted(image["files"], key=lambda f: int(f["offset"], 16)):
    argv += [f["offset"], f["path"]]
  return argv


async def flash(port: str, image: dict, on_output: Callable[[str, Optional[float]], None]):
  """Write the whole image with esptool. ``on_output(line, percent)`` is called per output line
  (``percent`` is set for progress lines). Raises FlashError on failure."""
  if not image["valid"]:
    raise FlashError(f"image is not valid: {image['error']}")
  argv = flash_argv(port, image)
  try:
    proc = await asyncio.create_subprocess_exec(
        *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, "PYTHONUNBUFFERED": "1", "NO_COLOR": "1", "TERM": "dumb"})
  except OSError as e:
    raise FlashError(f"could not start esptool: {e}") from e

  tail: list = []

  async def pump():
    buf = ""
    while True:
      chunk = await proc.stdout.read(4096)
      if not chunk:
        break
      buf += chunk.decode("utf-8", "replace")
      *lines, buf = re.split(r"[\r\n]+", buf)
      for line in lines:
        _emit(line)
    _emit(buf)

  def _emit(line: str):
    line = line.strip()
    if not line:
      return
    m = _PERCENT.search(line) if line.startswith("Writing at") else None
    tail.append(line)
    del tail[:-12]
    on_output(line, float(m.group(1)) if m else None)

  try:
    await asyncio.wait_for(pump(), FLASH_TIMEOUT)
    code = await asyncio.wait_for(proc.wait(), 10)
  except asyncio.TimeoutError:
    proc.kill()
    await proc.wait()
    raise FlashError(f"esptool timed out after {int(FLASH_TIMEOUT)} s") from None
  except asyncio.CancelledError:
    proc.kill()
    await proc.wait()
    raise
  if code != 0:
    reason = next((l for l in reversed(tail) if "rror" in l or "ailed" in l), tail[-1] if tail else "")
    raise FlashError(f"esptool exited with status {code}: {reason}")
