# astromech_server

HTTP server that exposes Galaxy's Edge astromech droid control via REST API. Bridges Home Assistant with physical droids using `libastromech`.

## Architecture

- `src/server.py` - Flask/Hypercorn ASGI server on port 5050. Instantiates a global `R2_Unit` with the `resistance_blue` personality. Runs the HTTP server and a `keep_alive` heartbeat loop concurrently via `asyncio.gather`.
- `src/secure.py` - Home Assistant long-lived access token (do not commit real tokens).

## API Endpoints

- `POST /droids/<droid_id>/beep/<sound_id>` - Play a sound by index. Optional `?turn_head` query param triggers concurrent head look-around. Returns `{ms, turn_head}`.
- `POST /droids/<droid_id>/demo` - Run a demo sequence: center head, look around while playing first 7 personality sounds.

## Home Assistant Integration

The server reports droid availability to Home Assistant at `http://colossus.home.mcgachey.org:8123` as `binary_sensor.r2_t2` (on/off). The `keep_alive` loop pings the droid every 30 seconds and updates HA state on success/failure.

## Beacon Broadcasting

Runs a location beacon (location ID 4) via `hcitool` alongside the server. This keeps nearby droids awake (6-hour sleep suppression) and prevents them from reacting to each other's personality beacons (2-hour interaction suppression). The beacon starts once at server startup and broadcasts continuously until shutdown.

## Deployment

Deploys to a host aliased `r2t2` (Raspberry Pi or similar BLE-capable device).

- `bin/deploy.sh` - Copies source to `r2t2:~/code/astromech_server` and restarts the systemd service.
- `bin/install.sh` - Initial setup: copies repo, creates virtualenv, installs systemd service.
- `bin/astromech_service.sh` - Systemd ExecStart script: activates virtualenv, installs deps, runs `src/server.py`.
- `astromech.service` - systemd unit file. Runs as user `mcgachey`, restarts always.

## Dependencies

Requires `libastromech>=1.0.0` (installed from PyPI or local wheel), plus Flask, Hypercorn, asgiref, requests.

## Known Droid MAC Address

- R2-T2: `F7:E6:74:95:E5:53` (hardcoded in `server.py`)
