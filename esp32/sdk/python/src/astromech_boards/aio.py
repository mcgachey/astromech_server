"""asyncio wrappers.

``AsyncDroidBoard`` and ``AsyncBeaconBoard`` expose the same methods as the
blocking classes as coroutines (each runs in a worker thread, so a slow droid
command never blocks the event loop). Properties and ``on_event`` pass straight
through; event callbacks still run on the reader thread, so hand work to the
loop with ``loop.call_soon_threadsafe``.

    async with AsyncDroidBoard.open("/dev/ttyUSB0") as droid:
        await droid.beep(2, turn_head=True)
"""

import asyncio
import functools

from .boards import BeaconBoard, DroidBoard
from .discovery import find_boards as _find_boards


class _AsyncProxy:
    _sync_cls = None

    def __init__(self, board):
        self._board = board

    @classmethod
    async def open(cls, *args, **kwargs):
        board = await asyncio.to_thread(cls._sync_cls, *args, **kwargs)
        return cls(board)

    def __getattr__(self, name):
        attr = getattr(self._board, name)
        if name.startswith("_") or not callable(attr) or name == "on_event":
            return attr

        @functools.wraps(attr)
        async def call(*args, **kwargs):
            return await asyncio.to_thread(attr, *args, **kwargs)

        return call

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()


class AsyncDroidBoard(_AsyncProxy):
    _sync_cls = DroidBoard


class AsyncBeaconBoard(_AsyncProxy):
    _sync_cls = BeaconBoard


async def find_boards(*args, **kwargs):
    return await asyncio.to_thread(_find_boards, *args, **kwargs)
