# astromech_server

HTTP server that exposes Galaxy's Edge astromech droid control via a REST API and bridges Home Assistant with physical droids over Bluetooth.

This is a monorepo of implementations of the same functionality, each targeting different hardware and OS configurations. Each implementation is independently buildable and deployable; nothing outside its own directory is required to build it, other than the shared `config/` it is pointed at.

| Directory | Target | Status |
|---|---|---|
| [`raspberrypi/`](raspberrypi/README.md) | Raspberry Pi, Docker, Python + `libastromech` | Active |
| [`esp32/`](esp32/README.md) | ESP32 boards (droid controller or beacon) managed over USB serial by a master; firmware + Python SDK | Builds; SDK tested against a fake board; not yet on hardware |
| [`raspberrypi_controller/`](raspberrypi_controller/README.md) | Master for the ESP32 boards: HTTP service on a Pi (Docker) driving them over USB serial; `POST /demo` beeps | Written; untested |

**New here?** See [`ONBOARDING.md`](ONBOARDING.md) for setting up the ESP32 boards, the controller and the web UI.

## Shared

- `config/` - droid configuration (`droids.yml`) common to all implementations.
- `docs/` - shared documentation, including the REST API contract all implementations should follow.

## Adding an implementation

Create a new top-level directory (e.g. `esp32/`) with its own README and build/deploy tooling, and add it to the table above and to `CLAUDE.md`.
