# Docs

Shared documentation for all implementations.

## REST API contract

The Raspberry Pi implementation exposes this API on port 5050. The ESP32 boards do not serve REST or talk to Home Assistant: they speak a serial protocol (`esp32/docs/PROTOCOL.md`) to a master controller, which is expected to provide this REST API and HA reporting on their behalf (the `beep` and `demo` commands map onto the serial `beep` and `demo`).

- `POST /droids/<droid_id>/beep/<sound_id>` - play a sound by index. Optional `?turn_head` triggers a concurrent head look-around. Returns `{ms, turn_head}`.
- `POST /droids/<droid_id>/demo` - run a demo sequence: center head, look around while playing the first 7 personality sounds.

## Home Assistant

Droid availability is reported as a binary sensor (on/off) using the `home_assistant_entity` from `config/droids.yml`.
