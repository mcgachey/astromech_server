# raspberrypi_controller

Master controller for the ESP32 boards in `../esp32`: a small HTTP service that
runs on a Raspberry Pi with the droid board connected over USB. It talks to the
board with the `astromech_boards` SDK (`../esp32/sdk/python`).

## Web UI (port 5050, `/`)

Open `http://<pi>:5050/`. There is one tab per board (droid controller or beacon), found
automatically by scanning the serial ports (and rescanned every 20 s while a known board is
offline; **Scan for boards** forces it). Each tab has:

- **Status**: connection, firmware, uptime, and role-specific state.
- **Controls**: droid tabs have beep (sound picker, turn head), volume, head moves, demo,
  connect/disconnect/check/diagnose; beacon tabs have start/stop. The *Board* menu has
  ping, reboot and factory reset. Wheel `move`/`stop` is deliberately not exposed.
- **Configuration**: droid alias/address/type/personality or beacon kind/location ID, written
  to the board; plus controller-side name, notes and demo sound.
- **Firmware**: the running version, and a picker to install any firmware image of the board's
  role that was pushed to the controller (see below). The board is disconnected while it is written.
- **Home Assistant** (droid tabs): enable availability updates for the droid and set its entity
  ID, and send an update immediately (seeded from `home_assistant_entity` in `droids.yml`).
- **Personalities tab** (after API): catalogues a droid's personality chip. Pick a droid and a range
  of audio groups; the droid plays each sound (`play` command, raw group:sound), you say whether a
  sound played, then time it (Start timing plays it again; click *Sound ended*, or press Space/Enter,
  when it stops). The timings appear as YAML (`sounds: [{group, ms, sound}]`, the format of
  `config/personalities/*.yml`) in a text box to copy into a file; they are kept in the browser until
  cleared. Needs droid firmware with the `play` command. This is the UI version of libastromech's
  `discover_sounds.py`; timings include your reaction time.
- **API tab**: Swagger UI for the JSON API below, with *Try it out* to send real requests.
- **Messages**: live log of board events, firmware logs, and every command and result the
  controller sends, filterable, downloadable and clearable.

The **Firmware** tab (right-hand tabs) lists the images on the controller by role, with their
version, build, checksum status and the boards running them, and **Scan for new firmware** to pick
up images pushed since the last scan.

The **Home Assistant** tab (right-hand tabs, before API) holds the connection settings: enable, URL, long-lived
access token, resend interval, request timeout, HTTPS verification, and a **Test connection**
button that checks the values in the form (saved or not). While enabled, the controller posts
`on`/`off` (board online and droid connected) to each enabled droid's entity via
`POST /api/states/<entity>` when it changes and every interval. The token is stored in
`home_assistant.json` (mode 0600) and is never returned by the API.

Frontend: React + TypeScript + Mantine in `ui/` (Vite). The Docker build compiles it into
`src/static`. For development: `cd ui && npm install && npm run dev` (proxies `/api` to
`localhost:5050`, or set `CONTROLLER_URL`).

## Storage

Everything the UI keeps lives in the data directory (`DATA_DIR`, `/data` in the container,
`/var/lib/astromech-controller` on the host by default; override with `CONTROLLER_DATA`):

- `boards.json`: known boards with their names, notes and demo sound.
- `home_assistant.json`: Home Assistant connection settings (includes the token).
- `logs/<device_id>.jsonl`: per-board logs, rotated at about 1 MB (the last 1000 entries are
  shown). Both survive restarts and image rebuilds. "Forget board" deletes a board's log.

Settings stored *on* the boards (droid address, beacon kind, ...) stay in their NVS.

## Firmware

Images are built on a build machine and copied to the Pi by `make install` in `../esp32`
(see its README) into the firmware directory: `/var/lib/astromech-controller/firmware` on the host
by default (override with `FIRMWARE_DIR`), mounted read-only at `/firmware`. It holds
`<role>/<version>/manifest.json` plus the image files. The controller validates every file's
sha256 and the role, and re-checks the image right before writing it.

Installing writes the full image (bootloader, partition table, `boot_app0.bin`, app) with
`esptool`, so it also works on a blank or boot-looping board, and the board's saved settings (NVS)
are kept. While it runs the controller releases the board's serial port and does not probe it, then
rescans until the board answers and checks that it reports the new version. A board can only be
given firmware of its own role. If a flash fails the board may need to be put in the bootloader by
hand (hold BOOT while pressing EN) and the install retried.

Tests (with the SDK on the path): `cd tests && PYTHONPATH=../../esp32/sdk/python/src python -m unittest discover`.

## JSON API (used by the UI)

`GET /api/boards`, `POST /api/boards/scan`, `PATCH|DELETE /api/boards/<device_id>`,
`GET /api/boards/<id>/state`, `PUT /api/boards/<id>/config`,
`POST /api/boards/<id>/commands/<cmd>` (JSON body = args),
`GET|DELETE /api/boards/<id>/logs[?since=<seq>]`,
`GET /api/firmware[?role=]`, `POST /api/firmware/scan`, `GET|POST /api/boards/<id>/firmware` (POST body `{version}` starts a flash and returns 202), `GET|PUT /api/home_assistant`,
`POST /api/boards/<id>/home_assistant/send` (send a droid's state now), `POST /api/home_assistant/test` (body = settings to test; blank token uses the saved one). A board's
`PATCH` also takes `ha_enabled` and `ha_entity`. Errors are `{error, message}`.

The OpenAPI spec is `src/openapi.yaml`, served as JSON at `/api/openapi.json` (keep it in sync
when endpoints change).

## Driving commands (local only)

`POST /api/boards/<id>/commands/<cmd>` also takes `motor` (`{motor: left|right, speed: 0-255, backward, ramp_ms}`;
persistent until the next `motor`/`stop`), `rotate_head` (`{direction: left|right}`, 1.5 s) and, for droids,
`stop` (both wheels). They are accepted only from loopback clients (the robotics server on the same Pi);
other clients get 403 `local_only`, and the web UI does not offer them.

## Legacy droid API

Same paths and responses as the `raspberrypi` server. `<id>` is the droid's alias, `device_id` or
MAC address from `droids.yml` (only droids with a `device_id`).

- `POST /droids/<id>/beep/<sound>[?turn_head]` - `{ms, turn_head}`.
- `POST /droids/<id>/demo` - head-only demo (first 7 sounds); `{}`.
- Errors: 404 `unknown_droid`, 503 `droid_unavailable` / `board_unavailable`, 504 `timeout`
  (body `{error, message}`).

## Demo API

- `POST /demo[?droid=<alias>]` - the droid (default: the first in `droids.yml` with a
  `device_id`) plays one sound (its `demo_sound`, default 0) and the call returns
  when it ends: `{ms, sound, droid}`. It does not move the droid.
  Errors: 404 `unknown_droid`, 503 `droid_unavailable` / `board_unavailable`, 504 `timeout`.

## Deploy

From your workstation, to a Pi you can ssh and sudo on:

    raspberrypi_controller/bin/deploy.sh <hostname> [config-dir]

It installs Docker if missing, copies the sources to `~/astromech-deploy` on the
Pi, keeps the config in `/etc/astromech-controller` (installing the repo's `config/droids.yml` if there is none, or copying
`[config-dir]/droids.yml` if given)
and runs `run_docker.sh` there. To run it directly on the Pi instead:

    raspberrypi_controller/bin/run_docker.sh <config-dir>

`<config-dir>` must contain `droids.yml` (the shared `config/droids.yml`). Droids with a
`device_id` (from the board's `hello`) are the ones the controller drives; it finds each
board by that ID, so the serial port name doesn't matter.
The script builds the image (build context is the directory holding
`astromech_server/`), then runs it with `--restart unless-stopped`, host
networking, `/dev` mounted for the serial port, and the data directory mounted at `/data`.
Override the port with `PORT`, the config path with `CONTROLLER_CONFIG` and the data
directory with `CONTROLLER_DATA`, and the firmware directory with `FIRMWARE_DIR`.

A board can be flashed from the UI once firmware has been pushed (see Firmware); a new board
can also be flashed by hand (`../esp32/README.md`). It must be configured with the droid's address.
