from asgiref.wsgi import WsgiToAsgi
import asyncio
from flask import Flask, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
import requests
import yaml

from libastromech import Astromech, Personality, R2_Unit, BB_Unit, personality_beacon_payload, run_beacon
import secure

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
droids: dict[str, Astromech] = {}

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

def get_droid(droid_id: str) -> Astromech:
  droid = droids.get(droid_id)
  if not droid:
    raise KeyError(f"Unknown droid: {droid_id}")
  return droid

@app.route('/droids/<droid_id>/beep/<int:sound_id>', methods=['POST'])
async def beep(droid_id: str, sound_id: int):
  droid = get_droid(droid_id)
  turn_head = 'turn_head' in request.args
  sound = droid.personality.sounds[sound_id]
  if turn_head:
    await asyncio.gather(
      droid.play(sound, wait=False),
      droid.look_around(),
    )
  else:
    await droid.play(sound, wait=False)
  return {'ms': sound.ms, 'turn_head': turn_head}

@app.route('/droids/<droid_id>/demo', methods=['POST'])
async def demo(droid_id: str):
  droid = get_droid(droid_id)
  await run_demo(droid)
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

def _heartbeat_success(droid: Astromech):
  update_ha(True)

def _heartbeat_failure(droid: Astromech):
  update_ha(False)

def update_ha(available: bool):
  response = requests.post(
      url=f"http://colossus.home.mcgachey.org:8123/api/states/binary_sensor.r2_t2",
      headers={'Authorization': f"Bearer {secure.HA_TOKEN}"},
      json={
          'state': 'on' if available else 'off',
        },
  )
  if response.status_code != 200:
    print(f"Response: {response}")

async def main():
  config = Config()
  config.bind = '0.0.0.0:5050'
  beacon_payload = personality_beacon_payload(affiliation='silent', chip_id=0x01)
  load_droids('/config/droids.yml')
  for alias, droid in droids.items():
    if alias == droid.mac_address:
      continue
    print(f"Connecting to {alias} ({droid.mac_address})...", flush=True)
    await droid.connect()
    print(f"Connected to {alias}", flush=True)
  await asyncio.gather(
      serve(app, config),
      # droid.keep_alive(
      #   heartbeat_success=_heartbeat_success,
      #   heartbeat_failure=_heartbeat_failure,
      # ),
      run_beacon(beacon_payload),
  )

if __name__ == '__main__':
  asyncio.run(main())
