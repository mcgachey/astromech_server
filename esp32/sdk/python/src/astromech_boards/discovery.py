"""Find boards on the machine's serial ports."""

import logging
import threading
from dataclasses import dataclass

from .boards import BeaconBoard, Board, DroidBoard
from .errors import AstromechBoardsError
from .link import DEFAULT_BAUDRATE, Link
from .models import BoardInfo

log = logging.getLogger(__name__)

_ROLES = {"droid": DroidBoard, "beacon": BeaconBoard}


@dataclass
class FoundBoard:
    port: str
    info: BoardInfo


def candidate_ports():
    """USB serial ports (skips the built-in /dev/ttyS* UARTs)."""
    from serial.tools import list_ports

    return [p.device for p in list_ports.comports() if p.hwid and p.hwid != "n/a"]


def find_boards(ports=None, *, baudrate=DEFAULT_BAUDRATE, timeout=4.0):
    """Probe ports with ``hello`` and return the boards that answered.

    Probing opens each port, which can reset an attached board; ``timeout``
    leaves time for it to boot. Pass ``ports`` to limit the search. Match
    boards to droids by ``info.device_id``, not by port name, which can change
    when the USB devices re-enumerate.
    """
    ports = list(ports) if ports is not None else candidate_ports()
    found = []
    lock = threading.Lock()

    def probe(port):
        try:
            link = Link(port, baudrate=baudrate, handshake_timeout=timeout)
        except Exception as e:  # not a board, busy, no permission...
            log.debug("probe of %s failed: %s", port, e)
            return
        try:
            with lock:
                found.append(FoundBoard(port, BoardInfo.from_dict(link.hello)))
        finally:
            link.close()

    threads = [threading.Thread(target=probe, args=(p,), daemon=True) for p in ports]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(found, key=lambda f: f.port)


def open_board(port, *, baudrate=DEFAULT_BAUDRATE):
    """Open a port as whatever kind of board it turns out to be."""
    link = Link(port, baudrate=baudrate)
    role = link.hello.get("role")
    cls = _ROLES.get(role)
    if cls is None:
        link.close()
        raise AstromechBoardsError("unknown board role %r on %s" % (role, port))
    return cls(link=link)
