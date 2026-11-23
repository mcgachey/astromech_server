"""Exceptions raised by the SDK."""


class AstromechBoardsError(Exception):
    """Base class for everything this package raises."""


class BoardTimeout(AstromechBoardsError):
    """The board did not answer in time."""


class Disconnected(AstromechBoardsError):
    """The serial port closed or the board was unplugged."""


class ProtocolError(AstromechBoardsError):
    """The board spoke a different protocol, or the wrong role for this class."""


class BoardError(AstromechBoardsError):
    """The board understood the request and refused it.

    ``code`` is the protocol error code (docs/PROTOCOL.md); subclasses exist for
    the ones callers usually want to handle separately.
    """

    code = "internal"

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


class DroidUnavailable(BoardError):
    """The droid could not be reached (asleep, out of range, remote connected)."""


class NotConfigured(BoardError):
    """The droid board has no droid address configured."""


class InvalidArgument(BoardError):
    """A request argument was rejected."""


class Unsupported(BoardError):
    """The command isn't supported by this droid type (e.g. head moves on a BB)."""


class Busy(BoardError):
    """The board's command queue is full."""


_BY_CODE = {
    "droid_unavailable": DroidUnavailable,
    "not_configured": NotConfigured,
    "invalid_argument": InvalidArgument,
    "unsupported": Unsupported,
    "busy": Busy,
}


def board_error(code, message):
    return _BY_CODE.get(code, BoardError)(code, message)
