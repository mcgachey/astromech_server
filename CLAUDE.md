# astromech_server

Monorepo of implementations of the astromech HTTP server, each targeting different hardware/OS (`raspberrypi/` and `esp32/`; others planned). Each implementation is independently buildable and deployable. Shared files: `config/` (droid config, e.g. `droids.yml`) and `docs/` (including the REST API contract all implementations follow). Keep the API behavior consistent across implementations; document changes in `docs/README.md`.

**ESP32** (`esp32/`, Arduino + PlatformIO, see `esp32/README.md`): two firmwares from one project, env `droid` (one board per droid: BLE control) and env `beacon` (keep-awake beacon). The boards have no Wi-Fi; a separate master (e.g. a Pi, not built yet) manages them over USB serial using the NDJSON protocol in `esp32/docs/PROTOCOL.md` and the Python SDK in `esp32/sdk/python` (tests: `PYTHONPATH=src:tests python -m unittest discover -s tests`). Settings live in NVS. Firmware is versioned per env (`esp32/version/<env>.txt`); `make install` in `esp32/` packages the images (`dist/<role>/<version>/`) and rsyncs them to the controller (`install.conf`). Wheel movement (`move`/`stop`) is in the protocol, but never run it, or any code that calls it, against the droid without the user's permission (it sits on a shelf). Depends on the sibling checkout `../../libastromech/esp32` (NimBLE-Arduino 2.5.x). Build with `pio run` from `esp32/`; the toolchain is `pio` from `/opt/esp-venv`. Uploading writes the bootloader and partition table, so confirm with the user before flashing their board.

**raspberrypi_controller** (`raspberrypi_controller/`, see its README): Docker-deployed Flask/Hypercorn master (port 5050) for the ESP32 boards using the `astromech_boards` SDK; same layout as `raspberrypi/` (`Dockerfile`, `bin/run_docker.sh <config-dir>` with the shared `droids.yml`, whose droids need a `device_id`; `src/server.py`). `POST /demo` beeps and never moves the droid; a React + Mantine UI (`ui/`, served at `/`, JSON API under `/api`) configures, tests and monitors every board, one tab each. Names, notes and logs persist in the host data dir mounted at `/data` (`CONTROLLER_DATA`). The UI never exposes `move`/`stop`. It can flash a board from the pushed firmware images (Firmware tab and per-board section; `esptool` in the container) — never trigger a flash on the user's board without asking.

The sections below describe the Raspberry Pi implementation, rooted at `raspberrypi/`.

HTTP server that exposes Galaxy's Edge astromech droid control via REST API. Bridges Home Assistant with physical droids using `libastromech`.

## Architecture

- `raspberrypi/src/server.py` - Flask/Hypercorn ASGI server on port 5050. Instantiates a global `R2_Unit` with the `resistance_blue` personality. Runs the HTTP server and a `keep_alive` heartbeat loop concurrently via `asyncio.gather`.
- `raspberrypi/src/secure.py` - Home Assistant long-lived access token (do not commit real tokens).

## API Endpoints

- `POST /droids/<droid_id>/beep/<sound_id>` - Play a sound by index. Optional `?turn_head` query param triggers concurrent head look-around. Returns `{ms, turn_head}`.
- `POST /droids/<droid_id>/demo` - Run a demo sequence: center head, look around while playing first 7 personality sounds.

## Home Assistant Integration

The server reports droid availability to Home Assistant at `http://colossus.home.mcgachey.org:8123` as `binary_sensor.r2_t2` (on/off). The `keep_alive` loop pings the droid every 30 seconds and updates HA state on success/failure.

## Beacon Broadcasting

Runs a location beacon (location ID 4) via `hcitool` alongside the server. This keeps nearby droids awake (6-hour sleep suppression) and prevents them from reacting to each other's personality beacons (2-hour interaction suppression). The beacon starts once at server startup and broadcasts continuously until shutdown.

## Deployment

Runs as a Docker container on a Raspberry Pi (or similar BLE-capable device) aliased `r2t2`.

- `raspberrypi/bin/run_docker.sh <config-dir>` - Builds the image and runs the container with `--restart unless-stopped` for durability across reboots. Requires a config directory containing `droids.yml`.
- `raspberrypi/Dockerfile` - Builds from `python:3.12-slim`, installs `bluez`/`dbus`, bundles `libastromech` and server source.
- `config/droids.yml` (top level, shared) - Droid configuration (MAC addresses, personalities, HA entities).

### Deprecated (systemd service)

The following are deprecated in favor of Docker:
- `raspberrypi/bin/deploy.sh`, `bin/install.sh`, `bin/astromech_service.sh`, and `raspberrypi/astromech.service`

## Dependencies

Requires `libastromech>=1.0.0` (installed from PyPI or local wheel), plus Flask, Hypercorn, asgiref, requests.

## Known Droid MAC Address

- R2-T2: `F7:E6:74:95:E5:53` (hardcoded in `server.py`)
