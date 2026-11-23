# Serial protocol (version 1)

Each ESP32 board (`droid` or `beacon` firmware) has no network connectivity.
It is managed by a master (e.g. a Raspberry Pi) over its USB serial port.

## Framing

- 115200 baud, 8N1, UTF-8. One JSON object per line, terminated by `\n`
  (`\r\n` is tolerated). Maximum line length is 1024 bytes; the board rejects
  longer requests with `bad_request`.
- The board ignores lines that do not start with `{`. The ESP32 ROM prints
  boot text on the same port; the master must likewise ignore non-JSON lines.
- Opening the port from a host may toggle DTR/RTS and reset the board. After
  opening, send `hello` repeatedly (about every 0.75 s) until it answers.
  The SDK does this and avoids asserting DTR/RTS where it can.
- The board emits a `boot` event after every start.

## Messages

Request (master to board):

    {"id": 7, "cmd": "beep", "args": {"sound": 2, "turn_head": true}}

`id` is any integer chosen by the master; `args` is optional.

Response (board to master), exactly one per request:

    {"id": 7, "ok": true,  "result": {"ms": 1500, "turn_head": true}}
    {"id": 7, "ok": false, "error": {"code": "droid_unavailable", "message": "..."}}

If the request could not be parsed, `id` is `null`.

Event (board to master, unsolicited):

    {"event": "droid_state", "data": {"connected": true}}

Commands that talk to the droid are queued and run one at a time (queue depth
8, then `busy`). Responses to different commands may arrive out of order;
match them by `id`. Inline commands are answered immediately even while a
queued command is running.

## Error codes

| code | meaning |
|---|---|
| `bad_json` | the line was not valid JSON |
| `bad_request` | missing/invalid `cmd`, line too long |
| `unknown_command` | no such command for this firmware |
| `invalid_argument` | an argument is missing, wrong type or out of range |
| `busy` | command queue is full; retry later |
| `not_configured` | no droid address saved (droid firmware) |
| `droid_unavailable` | the droid could not be reached over BLE |
| `unsupported` | the configured droid type does not support the command (e.g. head movement on a BB unit) |
| `internal` | unexpected board-side failure |

## Common commands (both firmwares)

| cmd | args | result |
|---|---|---|
| `hello` | | `role` (`droid`/`beacon`), `firmware_version` (per role, from `version/<role>.txt`), `protocol`, `device_id`, `uptime_ms`, `build` (`<git commit> <compile date time>`) |
| `ping` | | `{}` |
| `reboot` | | `{}`; the board restarts and emits `boot` |
| `factory_reset` | | `{}`; erases all saved settings, restarts |
| `status` | | role-specific |
| `get_config` | | saved settings |

`device_id` is derived from the chip's MAC address (hex, byte order reversed). Use it, not the port name, to
identify a board; USB port numbers change when devices re-enumerate (or map
them with a udev rule keyed on the serial number).

## Droid firmware

| cmd | args | result |
|---|---|---|
| `status` | | `configured`, and if configured: `alias`, `address`, `type`, `personality`, `connected`, `last_seen_ms_ago` (null if never), plus `free_heap` |
| `get_config` | | `alias`, `address`, `type`, `personality`, `available_personalities` |
| `set_config` | any of `alias` (1-32 chars), `address` (`AA:BB:CC:DD:EE:FF`), `type` (`r2`/`bb`), `personality` | `restart_required: true`; takes effect after `reboot` |
| `sounds` | | `personality`, `sounds`: list of `{index, group, sound, ms}` |
| `connect` | | `connect_ms`; connects now (also enables auto-reconnect) |
| `disconnect` | | drops the link and stops auto-reconnect until `connect` |
| `check` | | `available`; pings, reconnecting if needed |
| `diagnose` | | scan + connect + ping report: `address`, `already_connected`, `advertising`, `rssi`, `address_type`, `other_droids`, `ble_devices_seen`, `connect_ok`, `connect_ms`, `ping_ok`, `ping_ms` |
| `beep` | `sound` (index, required), `turn_head` (bool), `wait` (bool) | `ms`, `turn_head` |
| `play` | `group` 0-255, `sound` 0-255 (both required) | `{}`; plays that clip by raw number, ignoring the personality, and returns without waiting for it to end (used to catalogue a chip's sounds) |
| `volume` | `level` 0-31 | `{}` |
| `center_head` | | `{}` (R-series only) |
| `look_around` | | `{}` (R-series only) |
| `move` | `direction` (`forward`, `backward`, `spin_cw`, `spin_ccw`, `turn_cw`, `turn_ccw`), `ms` 1-5000, `speed` 1-255 (optional) | `ms`; **drives the wheels**, answered when the move ends. BB units: forward/backward only (`unsupported` otherwise) |
| `stop` | | `{}`; stops the wheels at once. Inline, so it is answered while a `move` runs |
| `demo` | | `{}`; centres the head, looks around while playing the first 7 sounds (R-series only); never drives the wheels |

The board connects to the droid by itself after boot and re-connects when the
link drops (it pings every 30 s). Droid-action commands fail with
`droid_unavailable` after a 10 s connection attempt.

Events: `boot`, `droid_state` (`{"connected": bool}` on every change), `log`
(`{"msg": "..."}` diagnostics).

## Beacon firmware

The beacon starts at power-on from its saved configuration and needs no
master to keep working.

| cmd | args | result |
|---|---|---|
| `status` | | `advertising`, `kind`, `location_id` (when kind is `location`), `stopped_by_master`, `running_ms`, `watchdog_restarts` |
| `get_config` | | `kind`, `location_id` |
| `set_beacon` | `kind` (`silent`/`location`), `location_id` 0-255, `persist` (bool) | status; applies immediately |
| `stop_beacon` | | status |
| `start_beacon` | | status |

A 5 s watchdog restarts advertising if it stops, unless `stop_beacon` was
issued. Events: `boot`, `log`.
