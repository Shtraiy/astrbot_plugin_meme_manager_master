import asyncio
import unittest

from collector import wait_for_filter_reply_lock


class FakeEvent:
    def __init__(self, extras=None):
        self.extras = dict(extras or {})

    def get_extra(self, key):
        return self.extras.get(key)


class FilterFollowupLockTests(unittest.TestCase):
    def test_missing_filter_lock_returns_without_waiting(self):
        result = asyncio.run(wait_for_filter_reply_lock(FakeEvent()))

        self.assertEqual(result, "missing")

    def test_released_filter_lock_returns_without_relocking_it(self):
        async def scenario():
            lock = asyncio.Lock()
            event = FakeEvent({"astrbot_plugin_filter_reply_lock": lock})

            result = await wait_for_filter_reply_lock(event)

            return result, lock.locked()

        result, locked = asyncio.run(scenario())

        self.assertEqual(result, "released")
        self.assertFalse(locked)

    def test_held_filter_lock_blocks_until_all_followups_release_it(self):
        async def scenario():
            lock = asyncio.Lock()
            await lock.acquire()
            event = FakeEvent({"astrbot_plugin_filter_reply_lock": lock})
            waiter = asyncio.create_task(wait_for_filter_reply_lock(event))

            await asyncio.sleep(0)
            waiting_before_release = not waiter.done()
            lock.release()
            result = await waiter
            return waiting_before_release, result, lock.locked()

        waiting, result, locked = asyncio.run(scenario())

        self.assertTrue(waiting)
        self.assertEqual(result, "released")
        self.assertFalse(locked)

    def test_timeout_does_not_release_filter_owned_lock(self):
        async def scenario():
            lock = asyncio.Lock()
            await lock.acquire()
            event = FakeEvent({"astrbot_plugin_filter_reply_lock": lock})

            result = await wait_for_filter_reply_lock(event, timeout=0.01)

            still_locked = lock.locked()
            lock.release()
            return result, still_locked

        result, still_locked = asyncio.run(scenario())

        self.assertEqual(result, "timeout")
        self.assertTrue(still_locked)


if __name__ == "__main__":
    unittest.main()
