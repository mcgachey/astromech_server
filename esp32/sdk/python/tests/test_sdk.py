import asyncio
import threading
import unittest

from astromech_boards import (AsyncDroidBoard, BeaconBoard, BoardTimeout, Busy, DroidBoard,
                              DroidUnavailable, InvalidArgument, Link, ProtocolError)
from astromech_boards.errors import BoardError, Disconnected

from fake_board import HELLO, FakeSerial, Fail, droid_handler


def make_droid(**kw):
    state = {"connected": False}
    ser = FakeSerial(droid_handler(state), **kw)
    return DroidBoard(link=Link(serial_obj=ser, handshake_timeout=3)), ser, state


class LinkTests(unittest.TestCase):
    def test_handshake_ignores_noise_and_retries_while_booting(self):
        ser = FakeSerial(droid_handler(), ignore_first=2)
        link = Link(serial_obj=ser, handshake_timeout=5)
        self.assertEqual(link.hello["role"], "droid")
        link.close()

    def test_handshake_timeout(self):
        ser = FakeSerial(lambda c, a: None)
        with self.assertRaises(BoardTimeout):
            Link(serial_obj=ser, handshake_timeout=0.5)
        self.assertTrue(ser.closed)

    def test_protocol_mismatch(self):
        ser = FakeSerial(lambda c, a: dict(HELLO, protocol=2))
        with self.assertRaises(ProtocolError):
            Link(serial_obj=ser, handshake_timeout=1)

    def test_error_mapping_and_timeout(self):
        def h(cmd, args):
            if cmd == "hello":
                return dict(HELLO)
            if cmd == "busy":
                raise Fail("busy", "queue full")
            if cmd == "weird":
                raise Fail("something_new", "x")
            return None
        link = Link(serial_obj=FakeSerial(h), handshake_timeout=2)
        with self.assertRaises(Busy):
            link.request("busy")
        with self.assertRaises(BoardError) as cm:
            link.request("weird")
        self.assertEqual(cm.exception.code, "something_new")
        with self.assertRaises(BoardTimeout):
            link.request("silent", timeout=0.2)
        link.close()

    def test_concurrent_requests_match_ids(self):
        link = Link(serial_obj=FakeSerial(lambda c, a: dict(HELLO) if c == "hello" else {"echo": a["n"]}),
                    handshake_timeout=2)
        out = {}

        def go(n):
            out[n] = link.request("x", {"n": n})["echo"]

        ts = [threading.Thread(target=go, args=(n,)) for n in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(out, {n: n for n in range(20)})
        link.close()

    def test_close_fails_pending_and_later_requests(self):
        link = Link(serial_obj=FakeSerial(lambda c, a: dict(HELLO) if c == "hello" else None),
                    handshake_timeout=2)
        errs = []
        t = threading.Thread(target=lambda: errs.append(_catch(lambda: link.request("slow", timeout=5))))
        t.start()
        link.close()
        t.join(3)
        self.assertIsInstance(errs[0], Disconnected)
        with self.assertRaises(Disconnected):
            link.request("ping")


def _catch(fn):
    try:
        fn()
    except Exception as e:
        return e


class DroidTests(unittest.TestCase):
    def test_open_and_status(self):
        board, ser, _ = make_droid()
        self.assertEqual(board.info.device_id, "3ce90e8581f4")
        self.assertFalse(board.droid_connected)
        self.assertEqual(board.status().alias, "r2t2")
        board.close()

    def test_wrong_role(self):
        ser = FakeSerial(droid_handler())
        with self.assertRaises(ProtocolError):
            BeaconBoard(link=Link(serial_obj=ser, handshake_timeout=2))

    def test_beep_requires_droid(self):
        board, ser, state = make_droid()
        with self.assertRaises(DroidUnavailable):
            board.beep(1)
        board.connect()
        r = board.beep(1, turn_head=True)
        self.assertTrue(r.turn_head)
        with self.assertRaises(InvalidArgument):
            board.beep(99)
        sent = [m for m in ser.written if m["cmd"] == "beep"][1]
        self.assertEqual(sent["args"], {"sound": 1, "turn_head": True})
        board.close()

    def test_play_raw_clip(self):
        board, ser, state = make_droid()
        with self.assertRaises(DroidUnavailable):
            board.play(1, 2)
        board.connect()
        board.play(1, 2)
        with self.assertRaises(InvalidArgument):
            board.play(1, 300)
        sent = [m for m in ser.written if m["cmd"] == "play"][1]
        self.assertEqual(sent["args"], {"group": 1, "sound": 2})
        board.close()

    def test_move_and_stop(self):
        board, ser, _ = make_droid()
        with self.assertRaises(DroidUnavailable):
            board.move("forward", 100)
        board.connect()
        board.move("spin_cw", 200, speed=90)
        board.stop()
        sent = [m for m in ser.written if m["cmd"] == "move"][-1]
        self.assertEqual(sent["args"], {"direction": "spin_cw", "ms": 200, "speed": 90})
        with self.assertRaises(InvalidArgument):
            board.move("forward", 99999)
        board.close()

    def test_droid_state_events(self):
        board, ser, _ = make_droid()
        self.assertFalse(board.wait_for_droid(0.1))
        ser.event("droid_state", connected=True)
        self.assertTrue(board.wait_for_droid(2))
        ser.event("droid_state", connected=False)
        for _ in range(50):
            if not board.droid_connected:
                break
            threading.Event().wait(0.02)
        self.assertFalse(board.droid_connected)
        board.close()

    def test_diagnose_ignores_unknown_fields(self):
        board, _, _ = make_droid()
        d = board.diagnose()
        self.assertTrue(d.ok)
        self.assertEqual(d.rssi, -80)
        board.close()

    def test_sounds(self):
        board, _, _ = make_droid()
        self.assertEqual(board.sounds()[0].ms, 1500)
        board.close()

    def test_reboot_waits_for_boot_event(self):
        state = {"connected": False}
        base = droid_handler(state)
        holder = {}

        def h(cmd, args):
            if cmd == "reboot":
                threading.Timer(0.2, lambda: holder["ser"].event("boot", role="droid")).start()
                return {}
            return base(cmd, args)

        ser = holder["ser"] = FakeSerial(h)
        board = DroidBoard(link=Link(serial_obj=ser, handshake_timeout=2))
        board.reboot()
        self.assertEqual(board.info.role, "droid")
        board.close()

    def test_reboot_timeout(self):
        board, _, _ = make_droid()
        # the fake never emits boot for unknown 'reboot' -> it answers unknown_command
        with self.assertRaises(BoardError):
            board.reboot(timeout=0.2)
        board.close()


class AsyncTests(unittest.TestCase):
    def test_async_wrapper(self):
        async def run():
            ser = FakeSerial(droid_handler())
            sync = await asyncio.to_thread(
                lambda: DroidBoard(link=Link(serial_obj=ser, handshake_timeout=2)))
            async with AsyncDroidBoard(sync) as droid:
                st = await droid.status()
                self.assertEqual(st.alias, "r2t2")
                self.assertEqual(droid.info.role, "droid")
                await droid.connect()
                r = await droid.beep(1)
                self.assertEqual(r.ms, 1500)
            self.assertTrue(ser.closed)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
