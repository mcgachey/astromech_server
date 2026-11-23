# Onboarding: ESP32 boards and the controller

This guide takes you from bare hardware to a working setup: ESP32 boards flashed and
configured, the controller service running on a Raspberry Pi, and the web UI connected to your
droids. It covers the ESP32 implementation only; the older all-in-one Pi server is in
[`raspberrypi/README.md`](raspberrypi/README.md).

> **Status:** the firmware builds and the SDK and controller are tested against emulated
> boards, but the full chain has not been run on real hardware yet. Expect to adjust, and
> start with the beacon or a beep before anything else.

## 1. How the pieces fit

```
 droid <--BLE--> [ESP32 "droid" board] --USB serial--+
                                                     +--> Raspberry Pi: controller (Docker, port 5050)
 nearby droids <--BLE-- [ESP32 "beacon" board] --USB-+              |
                                                            browser: web UI at http://<pi>:5050/
```

- The ESP32 boards have **no Wi-Fi or network stack**. They are managed only over USB serial,
  using the protocol in [`esp32/docs/PROTOCOL.md`](esp32/docs/PROTOCOL.md).
- **Droid board**: one per droid. It holds the BLE connection (connects after power-up,
  heartbeat every 30 s, reconnects on its own) and plays sounds, moves the head, and so on.
- **Beacon board**: broadcasts the keep-awake beacon from power-on. It keeps nearby droids
  awake and calm, and keeps working with no master attached.
- **Controller** ([`raspberrypi_controller/`](raspberrypi_controller/README.md)): a Docker
  service on a Pi with the boards plugged in. It finds boards, serves the web UI, and keeps
  names and logs on the host.

## 2. What you need

| Item | Notes |
|---|---|
| ESP32 dev board per droid, plus one for a beacon | Classic ESP32 (`esp32dev`), with a USB data cable |
| Raspberry Pi | Any model that runs Docker, with the boards connected over USB (a powered hub is wise for several) |
| Workstation | To build/flash firmware (PlatformIO, `pio`) and to deploy over ssh |
| This repo, with `libastromech` checked out next to it | The firmware uses `../../libastromech/esp32` (see below) |
| Each droid's BLE address | `AA:BB:CC:DD:EE:FF` (see section 4) |

Directory layout the firmware build expects:

```
code/
  astromech_server/    this repo
  libastromech/        sibling checkout (esp32/ is used as a PlatformIO library)
```

## 3. Flash the boards

Build once, then flash each board with its own firmware. From the repo root:

```bash
cd esp32
pio run                                        # builds both firmwares (first run downloads toolchains)

pio run -e droid  -t upload --upload-port /dev/ttyUSB0   # board for a droid
pio run -e beacon -t upload --upload-port /dev/ttyUSB1   # board for the beacon
```

Use the port your board actually shows up as (`/dev/ttyUSB*`, `/dev/ttyACM*`, `/dev/esp32`
if you have a udev symlink; `pio device list` shows them).

Things to know:

- Uploading writes the **bootloader and partition table**. That is normal for a first flash.
  Saved settings (NVS) survive later app uploads, but double-check before reflashing a board
  that is already in service.
- If it can't connect, hold **BOOT** while tapping **EN**/RESET, then retry.
- Flash one board at a time and label each (the role is also reported by the board itself).
- Check a board came up. A serial monitor isn't much use (the board speaks JSON lines, and
  debug output is sent as `log` events rather than raw text), so use the controller UI in
  section 6, or the SDK:

  ```bash
  pip install ./sdk/python            # from esp32/
  python -c "from astromech_boards import find_boards; print(find_boards())"
  ```

  A working board shows up with its `role` (`droid` or `beacon`), firmware version and
  `device_id`.

### Beacon board

Nothing to configure for it to work: it starts broadcasting a **silent** beacon at power-on
(keeps droids awake and prevents them reacting to each other). To broadcast a location beacon
instead (the legacy server used location ID 4), set it in the UI (section 6) or:

```python
from astromech_boards import BeaconBoard
with BeaconBoard("/dev/ttyUSB1") as b:
    print(b.set_beacon("location", location_id=4, persist=True))
```

`persist=True` saves it for the next power-on. A 5 s watchdog restarts advertising if it stops,
unless you stopped it from the master.

### Droid board

Needs the droid's address saved on it. See the next section.

## 4. Connect a droid board to a droid

You need three things for the droid: its **BLE address**, its **type**, and a **personality**.

**1. Find the BLE address.** Known droids are in [`config/droids.yml`](config/droids.yml)
(`mac_address`). For a new droid, use any BLE scanner while the droid is awake (for example a
phone app, or `bluetoothctl scan on` on a Linux machine) and look for a device named like a
droid. Once a droid board is configured, **Diagnose** in the UI also lists other droids in
range (`other_droids`).

**2. Free the droid.** A droid accepts one BLE connection at a time. Close the Disney
Play/Galaxy's Edge app and stop the legacy `raspberrypi` server (or any other controller)
for that droid, or the board will report `droid_unavailable`. Wake the droid first.

**3. Save the settings on the board.** Either in the UI (Configuration card on the droid's
tab) or with the SDK:

```python
from astromech_boards import DroidBoard
with DroidBoard("/dev/ttyUSB0") as b:
    b.configure(address="F7:E6:74:95:E5:53", type="r2",
                personality="resistance_blue", alias="r2-t2")   # saves, then reboots
    print(b.diagnose())
```

| Setting | Values |
|---|---|
| `address` | `AA:BB:CC:DD:EE:FF` |
| `type` | `r2` (R-series, has a movable head) or `bb` (BB unit; no head commands) |
| `personality` | one of the board's `available_personalities` (e.g. `resistance_blue`) |
| `alias` | 1-32 characters |

Settings are written to the board's NVS and apply after a reboot (the UI and `configure()`
reboot for you). From then on the board connects to the droid by itself on every power-up.

**4. Verify the link.** **Diagnose** (UI) or `diagnose()` scans, connects and pings. Look at:

- `advertising: true` and `connect_ok: true` / `ping_ok: true`: you're done.
- `rssi` around **-80 dBm or worse** is a marginal link; move the board closer to the droid.
- `advertising: false`: the droid is asleep, out of range, or already connected elsewhere.

## 5. Set up the server (the controller)

The controller runs in Docker on the Pi. It needs a `droids.yml` and a data directory.

**Add each droid to `config/droids.yml`** with the board's `device_id` so the controller can
name it and serve `POST /demo`. The `device_id` is on the board's tab in the UI, or in the
SDK's `find_boards()` output. It is derived from the chip's MAC, and stays the same if the USB
port number changes.

```yaml
droids:
  - alias: r2-t2
    mac_address: "F7:E6:74:95:E5:53"
    device_id: "f481850ee93c"       # from the board's hello
    personality: resistance_blue
    type: r2
    demo_sound: 0                   # optional: sound used by POST /demo
```

Boards don't have to be listed to appear in the UI; listing a droid just gives it a first
name and demo sound. Beacons are discovered automatically.

### Option A: deploy from your workstation (recommended)

Needs ssh and sudo on the Pi:

```bash
raspberrypi_controller/bin/deploy.sh pi@<hostname> [config-dir]
```

It installs Docker if missing, copies the sources over, keeps config in
`/etc/astromech-controller` (installing the repo's `config/droids.yml` the first time, or the
`droids.yml` from `[config-dir]` if you pass one), builds the image (this includes the web UI)
and starts the container with `--restart unless-stopped`, so it survives reboots.

### Option B: run directly on the Pi

```bash
raspberrypi_controller/bin/run_docker.sh <config-dir>      # directory containing droids.yml
```

### Where things live on the Pi

| What | Where |
|---|---|
| Config (`droids.yml`) | `/etc/astromech-controller` (deploy script) or the `<config-dir>` you pass |
| Board names, notes, logs | `/var/lib/astromech-controller` (override with `CONTROLLER_DATA`), mounted at `/data` |
| Port | 5050 (override with `PORT`) |

The data directory persists across restarts and rebuilds. The container runs privileged with
`/dev` mounted so it can see boards that re-enumerate.

**After updating `droids.yml`**, re-run the deploy (or `run_docker.sh`) to restart the container.

## 6. Connect and use it

1. Plug the flashed boards into the Pi and make sure the controller container is running:
   `sudo docker ps --filter name=astromech-controller` and
   `sudo docker logs -f astromech-controller`.
2. Open **`http://<pi-hostname>:5050/`** in a browser on the same network.
3. Each board appears as a tab (within about 20 s, or press **Scan for boards**). A green dot
   means it's online.
4. On a **droid tab**: check that *droid connected* is shown, pick a sound and press **Beep**.
   Configure the droid under *Configuration* if you haven't yet. Use **Diagnose** when it won't
   connect.
5. On a **beacon tab**: confirm it shows *advertising*, and change its type under
   *Configuration* if needed.
6. Watch the **Messages** panel on any tab for commands, results, board events and firmware
   logs. It is stored on the Pi, so it is still there after a restart.

Quick API check from any machine (this beeps the first droid in `droids.yml` that has a
`device_id`, and never moves it):

```bash
curl -X POST http://<pi-hostname>:5050/demo
# {"droid":"r2-t2","ms":1500,"sound":0}
```

## 7. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| No tabs appear | The board isn't seen as a USB serial device: check the cable (data, not charge-only), `lsusb`, and `ls /dev/ttyUSB* /dev/ttyACM*` on the Pi. Check `docker logs astromech-controller`. |
| Board tab says offline with an error | Another program holds the serial port, or the board is mid-boot. Wait 20 s, or press **Scan for boards**. |
| `droid_unavailable` | Droid asleep, out of range, or connected to something else (phone app, legacy server). Wake it, close other controllers, run **Diagnose**. |
| `not_configured` | No droid address saved on that board yet (section 4). |
| Upload fails to connect | Hold BOOT while tapping EN, retry; check `--upload-port`. |
| Permission denied on the serial port (workstation) | Add your user to the `dialout` group and log in again. |
| Board numbers change after a re-plug | Expected: the controller matches boards by `device_id`, not port, so nothing to do. |
| Head commands rejected | The droid is configured as `bb`; BB units have no head. |

## 8. Safety

- **Wheel movement** (`move`/`stop`) exists in the firmware protocol but is intentionally not
  in the UI or the controller API. Don't call it from your own scripts unless the droid is
  somewhere safe.
- **Factory reset** (in the *Board* menu) erases the board's saved settings, including the
  droid address; you'll need to repeat section 4.
- The controller has **no authentication**. Keep it on a trusted network.

## Where to read more

- [`esp32/README.md`](esp32/README.md): firmware, build, flash
- [`esp32/docs/PROTOCOL.md`](esp32/docs/PROTOCOL.md): serial protocol and error codes
- [`esp32/sdk/python/README.md`](esp32/sdk/python/README.md): Python SDK
- [`raspberrypi_controller/README.md`](raspberrypi_controller/README.md): controller, API, storage
