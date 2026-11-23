"""SDK for the astromech ESP32 boards. See esp32/docs/PROTOCOL.md."""

from .aio import AsyncBeaconBoard, AsyncDroidBoard
from .boards import BeaconBoard, Board, DroidBoard
from .discovery import FoundBoard, find_boards, open_board
from .errors import (AstromechBoardsError, Busy, BoardError, BoardTimeout, Disconnected,
                     DroidUnavailable, InvalidArgument, NotConfigured, ProtocolError,
                     Unsupported)
from .link import Link
from .models import BeaconStatus, BeepResult, BoardInfo, Diagnosis, DroidStatus, Sound

__all__ = [
    "AsyncBeaconBoard", "AsyncDroidBoard", "AstromechBoardsError", "BeaconBoard", "BeaconStatus",
    "BeepResult", "Board", "BoardError", "BoardInfo", "BoardTimeout", "Busy", "Diagnosis",
    "Disconnected", "DroidBoard", "DroidStatus", "DroidUnavailable", "FoundBoard",
    "InvalidArgument", "Link", "NotConfigured", "ProtocolError", "Sound", "Unsupported",
    "find_boards", "open_board",
]
__version__ = "0.1.0"
