"""Plain data returned by the boards."""

from dataclasses import dataclass, field
from typing import List, Optional


def _pick(cls, d):
    names = cls.__dataclass_fields__
    return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class BoardInfo:
    role: str
    firmware_version: str
    protocol: int
    device_id: str  # the chip's MAC; stable across USB re-enumeration
    uptime_ms: int = 0
    build: str = ""

    @classmethod
    def from_dict(cls, d):
        return _pick(cls, d)


@dataclass
class Sound:
    index: int
    group: int
    sound: int
    ms: int  # clip duration


@dataclass
class BeepResult:
    ms: int
    turn_head: bool


@dataclass
class DroidStatus:
    configured: bool
    alias: Optional[str] = None
    address: Optional[str] = None
    type: Optional[str] = None
    personality: Optional[str] = None
    connected: bool = False
    last_seen_ms_ago: Optional[int] = None  # None if never reached
    free_heap: int = 0

    @classmethod
    def from_dict(cls, d):
        return _pick(cls, d)


@dataclass
class Diagnosis:
    """Result of a droid connection test (see DroidBoard.diagnose)."""

    address: str = ""
    already_connected: bool = False
    advertising: Optional[bool] = None  # was the droid seen in the BLE scan?
    rssi: Optional[int] = None  # dBm; about -80 or worse is a marginal link
    address_type: Optional[int] = None
    other_droids: List[dict] = field(default_factory=list)  # other DROID devices in range
    ble_devices_seen: Optional[int] = None
    connect_ok: Optional[bool] = None
    connect_ms: Optional[int] = None
    ping_ok: Optional[bool] = None
    ping_ms: Optional[int] = None
    error: Optional[str] = None

    @property
    def ok(self):
        return bool(self.ping_ok)

    @classmethod
    def from_dict(cls, d):
        return _pick(cls, d)


@dataclass
class BeaconStatus:
    advertising: bool
    kind: str  # "silent" or "location"
    location_id: Optional[int] = None
    stopped_by_master: bool = False
    running_ms: int = 0
    watchdog_restarts: int = 0

    @classmethod
    def from_dict(cls, d):
        return _pick(cls, d)
