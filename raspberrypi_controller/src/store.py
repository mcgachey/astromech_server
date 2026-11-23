"""Persistent storage under the data directory (a host volume in Docker).

    <data>/boards.json        registry of known boards + their UI settings
    <data>/logs/<id>.jsonl    one JSON log entry per line, per board (rotated by size)
"""
import json
import logging
import os
import tempfile
import threading
from collections import deque

log = logging.getLogger("controller.store")

MAX_LOG_BYTES = 1_000_000   # rotate to <id>.jsonl.1 beyond this
KEEP_ENTRIES = 1000         # per board, kept in memory and served to the UI


class Store:
  def __init__(self, data_dir: str):
    self.data_dir = data_dir
    self.log_dir = os.path.join(data_dir, "logs")
    self.boards_path = os.path.join(data_dir, "boards.json")
    os.makedirs(self.log_dir, exist_ok=True)
    self._lock = threading.Lock()

  # ---- registry --------------------------------------------------------

  def load_boards(self) -> dict:
    try:
      with open(self.boards_path) as f:
        data = json.load(f)
      return data if isinstance(data, dict) else {}
    except FileNotFoundError:
      return {}
    except (OSError, ValueError) as e:
      log.error("could not read %s (%s); starting with an empty registry", self.boards_path, e)
      return {}

  def save_boards(self, boards: dict):
    with self._lock:
      fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=".boards-")
      try:
        with os.fdopen(fd, "w") as f:
          json.dump(boards, f, indent=2, sort_keys=True)
        os.replace(tmp, self.boards_path)  # atomic: never leaves a half-written file
      except BaseException:
        try:
          os.unlink(tmp)
        except OSError:
          pass
        raise

  # ---- small JSON files -------------------------------------------------

  def load_json(self, name: str) -> dict:
    try:
      with open(os.path.join(self.data_dir, name)) as f:
        data = json.load(f)
      return data if isinstance(data, dict) else {}
    except FileNotFoundError:
      return {}
    except (OSError, ValueError) as e:
      log.error("could not read %s (%s); using defaults", name, e)
      return {}

  def save_json(self, name: str, data: dict, private: bool = False):
    """Atomically write a JSON file (mode 0600 if ``private``, e.g. it holds a token)."""
    with self._lock:
      fd, tmp = tempfile.mkstemp(dir=self.data_dir, prefix=".tmp-")
      try:
        with os.fdopen(fd, "w") as f:
          json.dump(data, f, indent=2, sort_keys=True)
        if private:
          os.chmod(tmp, 0o600)
        os.replace(tmp, os.path.join(self.data_dir, name))
      except BaseException:
        try:
          os.unlink(tmp)
        except OSError:
          pass
        raise

  # ---- logs ------------------------------------------------------------

  def _log_path(self, device_id: str) -> str:
    safe = "".join(c for c in device_id if c.isalnum() or c in "-_")
    return os.path.join(self.log_dir, safe + ".jsonl")

  def load_log(self, device_id: str) -> deque:
    """The most recent entries of a board's log, oldest first."""
    entries = deque(maxlen=KEEP_ENTRIES)
    path = self._log_path(device_id)
    for p in (path + ".1", path):
      try:
        with open(p) as f:
          for line in f:
            try:
              entries.append(json.loads(line))
            except ValueError:
              pass  # a torn last line after a crash
      except FileNotFoundError:
        pass
    return entries

  def append_log(self, device_id: str, entry: dict):
    path = self._log_path(device_id)
    with self._lock:
      try:
        if os.path.exists(path) and os.path.getsize(path) > MAX_LOG_BYTES:
          os.replace(path, path + ".1")
        with open(path, "a") as f:
          f.write(json.dumps(entry, separators=(",", ":")) + "\n")
      except OSError as e:
        log.error("could not write log for %s: %s", device_id, e)

  def clear_log(self, device_id: str):
    path = self._log_path(device_id)
    with self._lock:
      for p in (path, path + ".1"):
        try:
          os.unlink(p)
        except FileNotFoundError:
          pass

  def delete_board_data(self, device_id: str):
    self.clear_log(device_id)
