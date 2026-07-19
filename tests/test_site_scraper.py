import importlib.util
import sys
import types
import unittest
from pathlib import Path


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


app_module = sys.modules.setdefault("app", types.ModuleType("app"))
log_module = sys.modules.setdefault("app.log", types.ModuleType("app.log"))
log_module.logger = _Logger()
app_module.log = log_module

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins.v2"
    / "tgsearch115"
    / "site_scraper.py"
)
spec = importlib.util.spec_from_file_location("tgsearch115_site_scraper", MODULE_PATH)
site_scraper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = site_scraper
spec.loader.exec_module(site_scraper)


class _Response:
    def __init__(self, status_code=200, data=None, text="", content_type="application/json"):
        self.status_code = status_code
        self._data = data
        self.text = text
        self.headers = {"content-type": content_type}

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = []

    def get(self, _url, headers=None):
        self.headers.append(headers or {})
        return self.responses.pop(0)


class SiteScraperTest(unittest.TestCase):
    def test_year_filter_does_not_fall_back_to_fuzzy_results(self):
        scraper = site_scraper.FilejinScraper(app_auth="test")
        scraper._ensure_access = lambda: None
        scraper._search_suggest = lambda _term: (
            True,
            "ok",
            [{"title": "同名旧版", "year": 2020}],
        )

        items = scraper._get_items("同名作品", 2026)

        self.assertEqual([], items)

    def test_parse_downurl_json(self):
        data = {
            "code": 200,
            "panlist": {
                "url": ["https://115.com/s/abc", "https://115.com/s/abc"],
                "name": ["示例电影 2026 4K", "重复"],
                "p": ["a1b2", "a1b2"],
                "tname": ["115网盘", "115网盘"],
            },
            "downlist": {
                "list": {
                    "m": ["a" * 40],
                    "t": ["Example.Movie.2026.1080p"],
                    "s": ["4GB"],
                    "e": ["10"],
                    "n": ["2026-01-01"],
                }
            },
        }

        hits = site_scraper.FilejinScraper._parse_downurl_data(data)

        self.assertEqual(2, len(hits))
        self.assertEqual("115", hits[0].pan_type)
        self.assertEqual("a1b2", hits[0].receive_code)
        self.assertEqual("magnet", hits[1].pan_type)

    def test_parse_html_resources(self):
        text = """
        <a href="magnet:?xt=urn:btih:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb&amp;dn=Demo%20Movie">BT</a>
        <a href="https://115.com/s/demo">115</a> 提取码：c3d4
        <a href="https://115.com/s/demo">duplicate</a>
        """

        hits = site_scraper.FilejinScraper._parse_resources_from_html(text)

        self.assertEqual(2, len(hits))
        self.assertEqual("Demo Movie", hits[0].resource_title)
        self.assertEqual("115", hits[1].pan_type)
        self.assertEqual("c3d4", hits[1].receive_code)

    def test_fetch_resources_retries_403_as_page(self):
        page = '<a href="https://115.com/s/fallback">资源</a> 提取码: z9y8'
        client = _Client([
            _Response(status_code=403, text="forbidden", content_type="text/html"),
            _Response(status_code=200, text=page, content_type="text/html"),
        ])
        scraper = site_scraper.FilejinScraper(app_auth="test")
        scraper._http = client

        hits = scraper._fetch_resources("mv", "1")

        self.assertEqual(1, len(hits))
        self.assertEqual("https://115.com/s/fallback", hits[0].share_url)
        self.assertEqual("z9y8", hits[0].receive_code)
        self.assertEqual("document", client.headers[1]["Sec-Fetch-Dest"])
        self.assertEqual("", scraper.last_detail_error)

    def test_fetch_resources_uses_urllib_after_repeated_403(self):
        client = _Client([
            _Response(status_code=403, text="forbidden", content_type="text/html"),
            _Response(status_code=403, text="forbidden", content_type="text/html"),
        ])
        scraper = site_scraper.FilejinScraper(app_auth="test")
        scraper._http = client
        scraper._fetch_resources_urllib = lambda _dir, _id: [
            site_scraper.SiteHit(
                share_url="https://115.com/s/urllib",
                pan_type="115",
            )
        ]

        hits = scraper._fetch_resources("tv", "2")

        self.assertEqual(1, len(hits))
        self.assertEqual("https://115.com/s/urllib", hits[0].share_url)
        self.assertEqual("", scraper.last_detail_error)


if __name__ == "__main__":
    unittest.main()
