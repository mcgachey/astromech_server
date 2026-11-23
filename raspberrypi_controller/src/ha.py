"""Home Assistant integration: settings, connection test and availability updates.

Settings are global (URL, token, ...) and live in <data>/home_assistant.json. Each droid has its
own `ha_enabled` / `ha_entity` in its board record (see manager.py). While enabled, a droid's
availability (board online and droid connected) is posted to the entity as a state, `on` or
`off`, through `POST /api/states/<entity_id>` (the same call the legacy raspberrypi server uses).
"""
import asyncio
import json
import logging
import re
import ssl
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

log = logging.getLogger("controller.ha")

ENTITY_RE = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")
DEFAULTS = {"enabled": False, "url": "", "token": "", "verify_tls": True,
            "interval": 30, "timeout": 10}
CHECK_EVERY = 5.0  # seconds between looking for changes; interval is the resend period


class HaError(Exception):
  def __init__(self, code: str, message: str):
    super().__init__(message)
    self.code, self.message = code, message


def normalize_url(url: str) -> str:
  url = (url or "").strip().rstrip("/")
  if not url:
    return ""
  if "://" not in url:
    url = "http://" + url
  parts = urlsplit(url)
  if parts.scheme not in ("http", "https") or not parts.hostname:
    raise ValueError("URL must look like http://host:8123")
  return url


def valid_entity(entity: str) -> bool:
  return bool(ENTITY_RE.match(entity or ""))


def _request(settings: dict, method: str, path: str, body=None):
  """One HA REST call (blocking). Returns (status, parsed JSON or None)."""
  req = urllib.request.Request(
      settings["url"] + path, method=method,
      data=None if body is None else json.dumps(body).encode(),
      headers={"Authorization": f"Bearer {settings['token']}", "Content-Type": "application/json"})
  ctx = None
  if settings["url"].startswith("https") and not settings.get("verify_tls", True):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
  try:
    with urllib.request.urlopen(req, timeout=settings.get("timeout", 10), context=ctx) as r:
      raw = r.read()
      status = r.status
  except urllib.error.HTTPError as e:
    status, raw = e.code, e.read()
  except (urllib.error.URLError, OSError, ValueError) as e:
    reason = getattr(e, "reason", e)
    raise HaError("unreachable", f"could not reach Home Assistant: {reason}") from e
  try:
    return status, json.loads(raw) if raw else None
  except ValueError:
    return status, None


def test_connection(settings: dict) -> dict:
  """Checks URL and token. Raises HaError describing the first problem found."""
  if not settings.get("url"):
    raise HaError("invalid_argument", "enter the Home Assistant URL first")
  if not settings.get("token"):
    raise HaError("invalid_argument", "enter a long-lived access token first")
  status, _ = _request(settings, "GET", "/api/")
  if status in (401, 403):
    raise HaError("unauthorized", "Home Assistant rejected the token")
  if status != 200:
    raise HaError("bad_response", f"unexpected HTTP {status} from {settings['url']}/api/")
  info = {}
  status, data = _request(settings, "GET", "/api/config")
  if status == 200 and isinstance(data, dict):
    info = {"location_name": data.get("location_name"), "version": data.get("version")}
  return info


class HomeAssistant:
  def __init__(self, store, manager):
    self.store, self.manager = store, manager
    self.settings = {**DEFAULTS, **store.load_json("home_assistant.json")}
    self.status: dict = {}  # device_id -> {state, ok, ts, error}
    self._sent: dict = {}   # device_id -> (entity, state, monotonic time)
    self._kick = asyncio.Event()

  # ---- settings --------------------------------------------------------

  def public_settings(self) -> dict:
    s = {k: v for k, v in self.settings.items() if k != "token"}
    s["token_set"] = bool(self.settings.get("token"))
    return s

  def _merged(self, fields: dict) -> dict:
    """Current settings with ``fields`` applied and validated. A blank token keeps the old one."""
    s = dict(self.settings)
    try:
      if "url" in fields:
        s["url"] = normalize_url(str(fields["url"] or ""))
      if fields.get("token"):
        s["token"] = str(fields["token"]).strip()
      if fields.get("clear_token"):
        s["token"] = ""
      if "enabled" in fields:
        s["enabled"] = bool(fields["enabled"])
      if "verify_tls" in fields:
        s["verify_tls"] = bool(fields["verify_tls"])
      if "interval" in fields:
        s["interval"] = int(fields["interval"])
        if not 5 <= s["interval"] <= 3600:
          raise ValueError("interval must be 5-3600 seconds")
      if "timeout" in fields:
        s["timeout"] = int(fields["timeout"])
        if not 1 <= s["timeout"] <= 60:
          raise ValueError("timeout must be 1-60 seconds")
    except (TypeError, ValueError) as e:
      raise HaError("invalid_argument", str(e)) from e
    if s["enabled"] and not (s["url"] and s["token"]):
      raise HaError("invalid_argument", "a URL and token are required to enable updates")
    return s

  def update_settings(self, fields: dict) -> dict:
    self.settings = self._merged(fields)
    self.store.save_json("home_assistant.json", self.settings, private=True)
    self._sent.clear()  # resend everything with the new settings
    self._kick.set()
    return self.public_settings()

  async def test(self, fields: dict) -> dict:
    """Test the saved settings, or what is in the form (unsaved) if ``fields`` has any."""
    s = self._merged({**fields, "enabled": False})
    return await asyncio.to_thread(test_connection, s)

  # ---- updates ---------------------------------------------------------

  def poke(self):
    """Something changed (droid settings); re-evaluate soon."""
    self._sent.clear()
    self._kick.set()

  async def _availability(self, device_id: str) -> bool:
    if device_id not in self.manager._boards:
      return False
    try:
      status = await self.manager._call(device_id, "status", lambda b: b.status(), quiet=True)
    except Exception:
      return False
    return bool(status.get("connected"))

  async def _push(self, device_id: str, entity: str, state: str, name: str):
    s = dict(self.settings)
    body = {"state": state, "attributes": {"friendly_name": name, "source": "astromech_controller"}}
    try:
      status, _ = await asyncio.to_thread(_request, s, "POST", f"/api/states/{entity}", body)
      if status not in (200, 201):
        raise HaError("bad_response", f"HTTP {status}" + (" (token rejected)" if status in (401, 403) else ""))
      self.status[device_id] = {"state": state, "ok": True, "ts": time.time(), "error": None}
      self._sent[device_id] = (entity, state, time.monotonic())
    except HaError as e:
      prev = self.status.get(device_id, {})
      if prev.get("ok", True) or prev.get("error") != e.message:
        self.manager.add_log(device_id, "error", f"Home Assistant update of {entity} failed: {e.message}",
                             level="warning")
      self.status[device_id] = {"state": state, "ok": False, "ts": time.time(), "error": e.message}
      self._sent[device_id] = (entity, None, time.monotonic())  # retry after the interval

  async def send_now(self, device_id: str) -> dict:
    """Post a droid's availability right away (manual; works even if updates are disabled)."""
    rec = self.manager._require(device_id)
    entity = rec.get("ha_entity", "")
    if rec["role"] != "droid":
      raise HaError("invalid_argument", "only droid boards have a Home Assistant entity")
    if not valid_entity(entity):
      raise HaError("invalid_argument", "set a valid entity ID for this droid first")
    if not (self.settings["url"] and self.settings["token"]):
      raise HaError("invalid_argument", "configure the URL and token on the Home Assistant tab first")
    state = "on" if await self._availability(device_id) else "off"
    await self._push(device_id, entity, state, rec["name"])
    result = self.status[device_id]
    if not result["ok"]:
      raise HaError("update_failed", result["error"])
    return {"ok": True, "entity": entity, "state": state}

  async def run(self):
    """Background task: keep the entities current."""
    while True:
      try:
        s = self.settings
        if s["enabled"] and s["url"] and s["token"]:
          for device_id, rec in list(self.manager.registry.items()):
            entity = rec.get("ha_entity", "")
            if rec["role"] != "droid" or not rec.get("ha_enabled") or not valid_entity(entity):
              self.status.pop(device_id, None)
              continue
            state = "on" if await self._availability(device_id) else "off"
            last = self._sent.get(device_id)
            due = (last is None or last[0] != entity or last[1] != state
                   or time.monotonic() - last[2] >= s["interval"])
            if due:
              await self._push(device_id, entity, state, rec["name"])
        else:
          self.status.clear()
      except Exception:
        log.exception("Home Assistant update pass failed")
      try:
        await asyncio.wait_for(self._kick.wait(), CHECK_EVERY)
      except asyncio.TimeoutError:
        pass
      self._kick.clear()
