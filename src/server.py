from asgiref.wsgi import WsgiToAsgi
import asyncio
from flask import Flask, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
import requests
import yaml

import traceback
from bleak.exc import BleakDBusError, BleakDeviceNotFoundError

from libastromech import Astromech, Personality, R2_Unit, BB_Unit, personality_beacon_payload, run_beacon, start_beacon
import secure

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
droids: dict[str, Astromech] = {}
ha_entities: dict[str, str] = {}
droid_status: dict[str, bool] = {}

DROID_TYPES = {
  'r2': R2_Unit,
  'bb': BB_Unit,
}

def load_droids(config_path: str):
  with open(config_path) as f:
    config = yaml.safe_load(f)
  aliases = {e['alias'] for e in config['droids']}
  for entry in config['droids']:
    droid_type = entry.get('type', 'r2')
    cls = DROID_TYPES[droid_type]
    personality = Personality(entry['personality']) if 'personality' in entry else None
    droid = cls(entry['mac_address'], personality=personality)
    droids[entry['alias']] = droid
    if entry['mac_address'] not in aliases:
      droids[entry['mac_address']] = droid
    if 'home_assistant_entity' in entry:
      ha_entities[entry['alias']] = entry['home_assistant_entity']

def get_droid(droid_id: str) -> Astromech:
  droid = droids.get(droid_id)
  if not droid:
    raise KeyError(f"Unknown droid: {droid_id}")
  return droid

DROID_UNAVAILABLE_ERRORS = (BleakDBusError, BleakDeviceNotFoundError)

@app.route('/droids/<droid_id>/beep/<int:sound_id>', methods=['POST'])
async def beep(droid_id: str, sound_id: int):
  droid = get_droid(droid_id)
  turn_head = 'turn_head' in request.args
  sound = droid.personality.sounds[sound_id]
  try:
    if turn_head:
      await asyncio.gather(
        droid.play(sound, wait=False),
        droid.look_around(),
      )
    else:
      await droid.play(sound, wait=False)
  except DROID_UNAVAILABLE_ERRORS as e:
    print(f"[http] {request.method} {request.path} failed: {e}", flush=True)
    return {'error': str(e)}, 503
  return {'ms': sound.ms, 'turn_head': turn_head}

@app.route('/droids/<droid_id>/demo', methods=['POST'])
async def demo(droid_id: str):
  droid = get_droid(droid_id)
  try:
    await run_demo(droid)
  except DROID_UNAVAILABLE_ERRORS as e:
    print(f"[http] {request.method} {request.path} failed: {e}", flush=True)
    return {'error': str(e)}, 503
  return {}

async def run_demo(droid: Astromech):
  await droid.center_head()
  await asyncio.gather(
    droid.look_around(),
    play_sounds(droid),
  )
  await droid.center_head()

async def play_sounds(droid: Astromech):
  for sound in droid.personality.sounds[0:7]:
    await droid.play(sound, wait=True)

def _update_ha_sync(entity: str, available: bool):
  try:
    response = requests.post(
        url=f"http://colossus.home.mcgachey.org:8123/api/states/{entity}",
        headers={'Authorization': f"Bearer {secure.HA_TOKEN}"},
        json={
            'state': 'on' if available else 'off',
          },
        timeout=10,
    )
    if response.status_code != 200:
      print(f"[heartbeat] HA update failed for {entity}: {response}", flush=True)
  except Exception as e:
    print(f"[heartbeat] HA update error for {entity}: {e}", flush=True)

async def update_ha(entity: str, available: bool):
  loop = asyncio.get_running_loop()
  await loop.run_in_executor(None, _update_ha_sync, entity, available)

async def check_droid(alias: str, entity: str):
  try:
    droid = droids.get(alias)
    if not droid:
      return
    try:
      await droid.ping()
      available = True
    except Exception:
      available = False
    await update_ha(entity, available)
    prev = droid_status.get(alias)
    if prev != available:
      label = 'connected' if available else 'disconnected'
      print(f"[heartbeat] {alias} {label}", flush=True)
      droid_status[alias] = available
  except Exception:
    print(f"[heartbeat] {alias} check failed unexpectedly:", flush=True)
    traceback.print_exc()

async def heartbeat_loop():
  while True:
    try:
      await asyncio.sleep(60)
      await asyncio.gather(*[
        check_droid(alias, entity)
        for alias, entity in ha_entities.items()
      ])
    except Exception:
      print("[heartbeat] cycle failed unexpectedly:", flush=True)
      traceback.print_exc()

async def connect_droids():
  for alias, droid in droids.items():
    if alias == droid.mac_address:
      continue
    print(f"Connecting to {alias} ({droid.mac_address})...", flush=True)
    try:
      await droid.connect()
      print(f"Connected to {alias}", flush=True)
    except Exception as e:
      print(f"Could not connect to {alias}: {e}", flush=True)
  await asyncio.gather(*[
    check_droid(alias, entity)
    for alias, entity in ha_entities.items()
  ])

async def _run_forever(name, coro_fn, *args):
  while True:
    try:
      await coro_fn(*args)
    except Exception:
      print(f"[server] {name} crashed, restarting in 5s:", flush=True)
      traceback.print_exc()
      await asyncio.sleep(5)

async def main():
  config = Config()
  config.bind = '0.0.0.0:5050'
  beacon_payload = personality_beacon_payload(affiliation='silent', chip_id=0x01)
  load_droids('/config/droids.yml')
  start_beacon(beacon_payload)
  try:
    await connect_droids()
  except Exception:
    print("[server] connect_droids failed, continuing:", flush=True)
    traceback.print_exc()
  await asyncio.gather(
      serve(app, config),
      _run_forever('beacon', run_beacon, beacon_payload),
      _run_forever('heartbeat', heartbeat_loop),
  )

if __name__ == '__main__':
  asyncio.run(main())
