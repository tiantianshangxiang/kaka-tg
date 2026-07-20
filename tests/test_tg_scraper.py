import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


app = sys.modules.setdefault("app", types.ModuleType("app"))
app_log = sys.modules.setdefault("app.log", types.ModuleType("app.log"))
app_log.logger = _Logger()

MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "tg_scraper.py"
spec = importlib.util.spec_from_file_location("tgsearch115_tg_scraper", MODULE_PATH)
tg_scraper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = tg_scraper
spec.loader.exec_module(tg_scraper)


class _Response:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, _url):
        self.calls += 1
        return self.responses.pop(0)


class TgScraperTest(unittest.TestCase):
    def test_429_retries_and_honors_configured_retry_path(self):
        scraper = tg_scraper.TgChannelScraper(max_retries=1)
        client = _Client([
            _Response(429, {"Retry-After": "5"}),
            _Response(200),
        ])
        delays = []
        original_sleep = tg_scraper.asyncio.sleep

        async def fake_sleep(delay):
            delays.append(delay)

        tg_scraper.asyncio.sleep = fake_sleep
        try:
            response = asyncio.run(
                scraper._get_with_backoff(client, "https://example.test", "demo", 1)
            )
        finally:
            tg_scraper.asyncio.sleep = original_sleep

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, client.calls)
        self.assertGreaterEqual(delays[0], 5)
        self.assertLess(delays[0], 6)


if __name__ == "__main__":
    unittest.main()
