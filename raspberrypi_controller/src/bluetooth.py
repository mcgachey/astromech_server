"""Bluetooth LE scanning for droids, using the Raspberry Pi's BlueZ stack (via bleak).

Same logic as scan() in droid/droid.py: a droid advertises with the name "DROID".
"""
import asyncio
import logging

from bleak import BleakScanner

log = logging.getLogger("bluetooth")

DROID_NAME = "DROID"
_lock = asyncio.Lock()


class BluetoothError(Exception):
  def __init__(self, code: str, message: str, status: int = 503):
    super().__init__(message)
    self.code, self.message, self.status = code, message, status


async def scan(timeout: float = 5.0, include_all: bool = False) -> list[dict]:
  """BLE devices seen within `timeout` seconds: droids only, unless `include_all`."""
  if _lock.locked():
    raise BluetoothError("scan_in_progress", "a Bluetooth scan is already running", 409)
  async with _lock:
    try:
      found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    except Exception as e:  # bleak raises BleakError, OSError, or dbus errors depending on the failure
      log.warning("Bluetooth scan failed: %s", e)
      raise BluetoothError("bluetooth_unavailable", f"Bluetooth scan failed: {e}") from e
  devices = []
  for device, adv in found.values():
    name = device.name or adv.local_name or ""
    if not include_all and name != DROID_NAME:
      continue
    devices.append({"name": name, "address": device.address, "rssi": adv.rssi, "droid": name == DROID_NAME})
  devices.sort(key=lambda d: (not d["droid"], -(d["rssi"] if d["rssi"] is not None else -999)))
  return devices
