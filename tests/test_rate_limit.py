import asyncio
import unittest

from bot.i18n import SUPPORTED_LANGUAGES, t
from bot.main import create_dispatcher
from bot.middlewares.rate_limit import RateLimitMiddleware, RateLimiter


class FakeClock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeUser:
    def __init__(self, id=7001):
        self.id = id


class FakeChat:
    def __init__(self, id=42):
        self.id = id


class FakeMessage:
    def __init__(self, user_id=7001, chat_id=42):
        self.from_user = FakeUser(user_id)
        self.chat = FakeChat(chat_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeCallback:
    def __init__(self, user_id=7001, chat_id=42):
        self.from_user = FakeUser(user_id)
        self.message = FakeMessage(user_id=user_id, chat_id=chat_id)
        self.answers = []

    async def answer(self, text=None, **kwargs):
        self.answers.append((text, kwargs))


async def ok_handler(event, data):
    data.setdefault("handled", 0)
    data["handled"] += 1
    return "ok"


class RateLimitTest(unittest.IsolatedAsyncioTestCase):
    def test_task_093_i18n_contains_rate_limit_message(self):
        for language in SUPPORTED_LANGUAGES:
            self.assertTrue(t("rate_limit_exceeded", language))

    def test_task_093_limiter_allows_limit_then_blocks_until_window_expires(self):
        clock = FakeClock()
        limiter = RateLimiter(max_events=2, window_seconds=10, clock=clock)

        self.assertTrue(limiter.allow("user:1"))
        self.assertTrue(limiter.allow("user:1"))
        self.assertFalse(limiter.allow("user:1"))

        clock.advance(10.01)
        self.assertTrue(limiter.allow("user:1"))

    def test_task_093_limiter_is_scoped_per_user_and_validates_settings(self):
        clock = FakeClock()
        limiter = RateLimiter(max_events=1, window_seconds=10, clock=clock)

        self.assertTrue(limiter.allow("user:1"))
        self.assertFalse(limiter.allow("user:1"))
        self.assertTrue(limiter.allow("user:2"))

        with self.assertRaises(ValueError):
            RateLimiter(max_events=0, window_seconds=10, clock=clock)
        with self.assertRaises(ValueError):
            RateLimiter(max_events=1, window_seconds=0, clock=clock)

    async def test_task_093_message_middleware_blocks_spam_and_answers_once(self):
        clock = FakeClock()
        middleware = RateLimitMiddleware(max_events=1, window_seconds=10, clock=clock)
        event = FakeMessage(user_id=7001)
        data = {}

        self.assertEqual("ok", await middleware(ok_handler, event, data))
        blocked = await middleware(ok_handler, event, data)

        self.assertIsNone(blocked)
        self.assertEqual(1, data["handled"])
        self.assertEqual(t("rate_limit_exceeded", "ru"), event.answers[0][0])

    async def test_task_093_callback_middleware_blocks_spam_with_alert(self):
        clock = FakeClock()
        middleware = RateLimitMiddleware(max_events=1, window_seconds=10, clock=clock)
        event = FakeCallback(user_id=7001)
        data = {}

        await middleware(ok_handler, event, data)
        blocked = await middleware(ok_handler, event, data)

        self.assertIsNone(blocked)
        self.assertEqual(1, data["handled"])
        self.assertEqual(t("rate_limit_exceeded", "ru"), event.answers[0][0])
        self.assertTrue(event.answers[0][1]["show_alert"])

    async def test_task_093_admin_chat_is_exempt_from_rate_limit(self):
        clock = FakeClock()
        middleware = RateLimitMiddleware(max_events=1, window_seconds=10, clock=clock)
        event = FakeMessage(user_id=7001, chat_id=-100123)
        data = {"config": type("Config", (), {"admin_chat_id": -100123})()}

        await middleware(ok_handler, event, data)
        await middleware(ok_handler, event, data)

        self.assertEqual(2, data["handled"])
        self.assertEqual([], event.answers)

    def test_task_093_default_dispatcher_installs_rate_limit_middleware(self):
        dispatcher = create_dispatcher()

        self.assertTrue(dispatcher.workflow_data["rate_limit_enabled"])
        self.assertIsInstance(dispatcher.workflow_data["rate_limit_middleware"], RateLimitMiddleware)


if __name__ == "__main__":
    unittest.main()
