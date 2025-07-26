from asgiref.wsgi import WsgiToAsgi
import asyncio
from flask import Flask, request
from hypercorn.config import Config
from hypercorn.asyncio import serve
import requests

from libastromech import Astromech, Personality, R2_Unit
import secure

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)
droid = R2_Unit("F7:E6:74:95:E5:53", personality=Personality('resistance_blue'))

@app.route('/droids/<droid_id>/beep/<int:sound_id>', methods=['POST'])
async def beep(droid_id: str, sound_id: int):
  turn_head = 'turn_head' in request.args
  sound = droid.personality.sounds[sound_id]
  async with droid as d:
    if turn_head:
      await asyncio.gather(
        droid.play(sound, wait=False),
        droid.look_around(),
      )
    else:
      await d.play(sound, wait=False),
  return {'ms': sound.ms, 'turn_head': turn_head}

@app.route('/droids/<droid_id>/demo', methods=['POST'])
async def demo(droid_id: str):
  print("Calling the thing")
  await run_demo()
  return {}

async def run_demo():
  async with droid as d:
    await d.center_head()
    await asyncio.gather(
      d.look_around(),
      play_sounds(d),
    )
    await d.center_head()

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
  await asyncio.gather(
      serve(app, config),
      droid.keep_alive(
        heartbeat_success=_heartbeat_success,
        heartbeat_failure=_heartbeat_failure,
      )
  )

if __name__ == '__main__':
  asyncio.run(main())
