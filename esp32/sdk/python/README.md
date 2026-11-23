# astromech_boards

Python SDK for the astromech ESP32 boards (see `../../docs/PROTOCOL.md`).

    pip install ./esp32/sdk/python        # needs pyserial

```python
from astromech_boards import find_boards, open_board, DroidBoard

for f in find_boards():                  # probes USB serial ports
    print(f.port, f.info.role, f.info.device_id)

with DroidBoard("/dev/esp32") as droid:
    droid.wait_for_droid(30)
    for s in droid.sounds(): print(s)
    droid.beep(2, turn_head=True)        # ask before moving a droid on a shelf!
```

- `DroidBoard`: `configure`, `status`, `sounds`, `connect`, `disconnect`,
  `check_alive`, `diagnose`, `beep`, `set_volume`, `center_head`,
  `look_around`, `demo`, `move`, `stop`, `wait_for_droid`, `droid_connected`
- `BeaconBoard`: `status`, `set_beacon`, `stop`, `start`
- Both: `ping`, `reboot`, `factory_reset`, `get_config`, `on_event`, `info`
- `astromech_boards.aio`: `AsyncDroidBoard.open(port)` / `AsyncBeaconBoard`
  with the same methods as coroutines
- Errors: `BoardError` subclasses (`DroidUnavailable`, `NotConfigured`,
  `InvalidArgument`, `Unsupported`, `Busy`) for refusals; `BoardTimeout`,
  `Disconnected`, `ProtocolError` for link problems

Tests (no hardware, uses a fake board):

    PYTHONPATH=src:tests python -m unittest discover -s tests
