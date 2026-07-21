import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins.v2"
    / "tgsearch115"
    / "resource_strategy.py"
)
spec = importlib.util.spec_from_file_location("tgsearch115_resource_strategy", MODULE_PATH)
resource_strategy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = resource_strategy
spec.loader.exec_module(resource_strategy)


def _torrent(url, pan_type, source="site", complete=True, text="中文字幕"):
    return SimpleNamespace(
        page_url=url,
        site_name={"site": "观影", "juying": "聚影"}.get(source, "TG频道"),
        title=text,
        description=text,
        _tg115_source=source,
        _tg115_pan_type=pan_type,
        _tg115_is_complete=complete,
    )


def _is_115(url):
    return "115.com/" in url


class ResourceStrategyTest(unittest.TestCase):
    def test_direct_failure_falls_back_to_cms(self):
        calls = []
        ok, message, source = resource_strategy.submit_magnet_with_fallback(
            "direct_then_cms",
            lambda: (calls.append("direct") or (False, "direct failed")),
            lambda: (calls.append("cms") or (True, "created")),
        )
        self.assertTrue(ok)
        self.assertEqual("cms", source)
        self.assertEqual(["direct", "cms"], calls)

    def test_orders_tg_then_guanying_115_then_guanying_magnet_then_juying(self):
        magnet = "magnet:?xt=urn:btih:" + "a" * 40
        torrents = [
            _torrent("https://115.com/s/juying", "115", source="juying"),
            _torrent(magnet, "magnet", text="1080P 中文字幕"),
            _torrent(magnet + "&dn=duplicate", "magnet", text="1080P 中文字幕"),
            _torrent("https://115.com/s/site", "115"),
            _torrent("https://115.com/s/tg", "115", source="tg", text="频道资源"),
        ]

        selected = resource_strategy.select_auto_candidates(
            torrents, True, False, _is_115
        )

        self.assertEqual([
            "https://115.com/s/tg",
            "https://115.com/s/site",
            magnet,
            "https://115.com/s/juying",
        ], [t.page_url for t in selected])

    def test_guanying_candidates_require_chinese_subtitle_marker(self):
        selected = resource_strategy.select_auto_candidates([
            _torrent("https://115.com/s/no-chs", "115", text="WEB-DL English"),
            _torrent("magnet:?xt=urn:btih:" + "f" * 40, "magnet", text="WEB-DL English"),
            _torrent("https://115.com/s/chs", "115", text="内封简繁字幕"),
        ], True, False, _is_115)
        self.assertEqual(["https://115.com/s/chs"], [t.page_url for t in selected])

    def test_auto_magnet_requires_chinese_1080p_or_4k(self):
        selected = resource_strategy.select_auto_candidates([
            _torrent("magnet:?xt=urn:btih:" + "1" * 40, "magnet", text="720P 中文字幕"),
            _torrent("magnet:?xt=urn:btih:" + "2" * 40, "magnet", text="1080P English"),
            _torrent("magnet:?xt=urn:btih:" + "3" * 40, "magnet", text="1080P 中文字幕"),
            _torrent("magnet:?xt=urn:btih:" + "4" * 40, "magnet", text="4K 简中"),
        ], True, False, _is_115)
        self.assertEqual([
            "magnet:?xt=urn:btih:" + "3" * 40,
            "magnet:?xt=urn:btih:" + "4" * 40,
        ], [item.page_url for item in selected])

    def test_cross_source_duplicate_keeps_higher_priority_tg_candidate(self):
        duplicate = "https://115.com/s/same"
        selected = resource_strategy.select_auto_candidates([
            _torrent(duplicate, "115", source="juying"),
            _torrent(duplicate, "115", source="tg", text="频道资源"),
        ], True, False, _is_115)
        self.assertEqual(1, len(selected))
        self.assertEqual("tg", selected[0]._tg115_source)

    def test_rejects_incomplete_tv_magnet(self):
        torrents = [
            _torrent("magnet:?xt=urn:btih:" + "b" * 40, "magnet", complete=False),
            _torrent("https://115.com/s/demo", "115"),
        ]

        selected = resource_strategy.select_auto_candidates(
            torrents, True, True, _is_115
        )

        self.assertEqual(["https://115.com/s/demo"], [t.page_url for t in selected])

    def test_ignores_non_guanying_magnet(self):
        selected = resource_strategy.select_auto_candidates(
            [_torrent("magnet:?xt=urn:btih:" + "c" * 40, "magnet", source="juying")],
            True,
            False,
            _is_115,
        )

        self.assertEqual([], selected)

    def test_cms_failure_continues_with_115_share(self):
        candidates = [
            _torrent("magnet:?xt=urn:btih:" + "d" * 40, "magnet"),
            _torrent("magnet:?xt=urn:btih:" + "e" * 40, "magnet"),
            _torrent("https://115.com/s/fallback", "115"),
        ]
        submitted_magnets = []
        transferred_shares = []

        result = resource_strategy.execute_auto_candidates(
            candidates=candidates,
            confirm_identity=lambda _candidate: SimpleNamespace(
                confirmed=True, recognition_attempted=True
            ),
            submit_magnet=lambda candidate: (
                submitted_magnets.append(candidate.page_url) or False,
                "CMS unavailable",
            ),
            transfer_share=lambda candidate: (
                transferred_shares.append(candidate.page_url) or True,
                "transferred",
            ),
        )

        self.assertEqual(1, len(submitted_magnets))
        self.assertEqual(["https://115.com/s/fallback"], transferred_shares)
        self.assertEqual("https://115.com/s/fallback", result.candidate.page_url)
        self.assertFalse(result.via_magnet)


if __name__ == "__main__":
    unittest.main()
