# astromech_server: ESP32 boards

Two firmwares from one PlatformIO project (Arduino framework, ESP32 classic,
`libastromech/esp32` over NimBLE). The boards have **no Wi-Fi and no network
stack**. Each is managed purely over its USB serial port by a separate master
controller (e.g. a Raspberry Pi), using the protocol in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md) and the Python SDK in
[`sdk/python`](sdk/python/README.md).

| env | role |
|---|---|
| `droid` | one board per droid: holds the BLE connection (auto-connect, 30 s heartbeat, auto-reconnect) and exposes beeps, volume, head moves and a demo |
| `beacon` | broadcasts the keep-awake beacon from power-on; the master can inspect or change it |

The master controller itself is not part of this repo yet. The REST API and
Home Assistant reporting of the Pi server will live there, not on the boards.

**Wheel movement (`move`, `stop`) is in the protocol, capped at 5 s per command; nothing in this repo calls it automatically.**

## Layout

- `src/common/`: NDJSON link over `Serial`, command dispatch, NVS settings
- `src/droid/`, `src/beacon/`: the two firmwares
- `sdk/python/`: `astromech_boards` package and tests
- `docs/PROTOCOL.md`: wire protocol

Depends on the sibling checkout `../../libastromech/esp32`.

## Build and flash

    cd esp32
    pio run                          # both envs
    pio run -e droid -t upload --upload-port /dev/esp32

Uploading writes the bootloader and partition table; the board's saved
settings (NVS) survive an app upload. If the port won't connect, hold BOOT
while tapping EN.

## Versions and installing on the controller

The droid and beacon firmwares are versioned separately: `version/droid.txt` and
`version/beacon.txt` hold `MAJOR.MINOR.PATCH`. The build injects it as `FIRMWARE_VERSION`
(plus the git commit as `FIRMWARE_BUILD_ID`), and the board reports both in `hello`
(`firmware_version`, `build`). `make build` (and so `package`/`install`) bumps the PATCH
number automatically when an env's sources changed since the last bump (tracked in
`version/.<env>.stamp`; `BUMP=0` skips it). Edit the file by hand for MINOR/MAJOR. This is
independent of `PROTOCOL_VERSION`.

To flash boards from the controller's web UI, build on any machine and publish the images
to the Pi:

    cp install.conf.example install.conf   # once: CONTROLLER_HOST, CONTROLLER_USER, FIRMWARE_DIR
    make install                           # pio run, package into dist/, rsync to the Pi

`make package` stops before the copy. Each release is `dist/<role>/<version>/` with the
bootloader, partition table, `boot_app0.bin`, `firmware.bin` and a `manifest.json` (flash offsets
are taken from PlatformIO, with a sha256 per file). An existing role/version is never silently
replaced: bump the version, or `make install FORCE=1`. On the Pi the directory defaults to
`/var/lib/astromech-controller/firmware`, and the ssh user needs write access to it
(`run_docker.sh` sets that up when run through sudo). Then use **Scan for new firmware** on the
controller's Firmware tab and install from a board's tab (`../raspberrypi_controller/README.md`).

## Configure a droid board

With the SDK (stored in the board's NVS, applied after reboot):

```python
from astromech_boards import DroidBoard
with DroidBoard("/dev/esp32") as b:
    b.configure(address="F7:E6:74:95:E5:53", type="r2",
                personality="resistance_blue", alias="r2t2")
    print(b.diagnose())
```

The board then connects to the droid by itself on every power-up.

## Notes

- Opening the serial port may reset the board; the SDK waits for it.
- Debug output goes to the master as `log` events, not raw text.
- Droids are weak BLE peers: expect RSSI near -80 dBm to be marginal. `diagnose()` reports it.
