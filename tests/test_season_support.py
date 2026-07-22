import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PATH = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "season_support.py"
spec = importlib.util.spec_from_file_location("tgsearch115_season_support", PATH)
season = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = season
spec.loader.exec_module(season)


class SeasonSupportTest(unittest.TestCase):
    def test_target_seasons_preserve_specials_and_multiple_values(self):
        subscribe = SimpleNamespace(
            season=0, seasons="S00,S02,S03", note={"target_seasons": [0, 2, 3]}
        )
        self.assertEqual([0, 2, 3], season.target_seasons(subscribe))

    def test_candidate_season_formats_and_ranges(self):
        self.assertEqual({2}, season.parse_seasons("第二季 Season 2 S02E01"))
        self.assertEqual({1, 2}, season.parse_seasons("第1-2季"))
        self.assertEqual({1, 2, 3}, season.parse_seasons("S01-S03"))
        self.assertEqual({0}, season.parse_seasons("House of the Dragon Specials"))
        self.assertEqual({1, 2, 3}, season.parse_seasons("全三季"))

    def test_specials_do_not_match_season_one(self):
        candidate = SimpleNamespace(title="示例剧 特别篇", description="")
        self.assertTrue(season.supports_target_season(candidate, 0))
        self.assertFalse(season.supports_target_season(candidate, 1))

    def test_missing_season_does_not_match_tv_target(self):
        candidate = SimpleNamespace(title="示例剧 1080P", description="")
        self.assertFalse(season.supports_target_season(candidate, 2))

    def test_s01_cache_cannot_satisfy_s02(self):
        cached = [SimpleNamespace(title="示例剧 S01", description="")]
        self.assertFalse(season.cache_covers_season(cached, 2))
        self.assertTrue(season.cache_covers_season(cached, 1))

    def test_cache_key_distinguishes_specials_and_seasons(self):
        key0 = season.source_cache_key("site", "示例", 2022, "TV", 0)
        key2 = season.source_cache_key("site", "示例", 2022, "TV", 2)
        key3 = season.source_cache_key("site", "示例", 2022, "TV", 3)
        self.assertEqual(3, len({key0, key2, key3}))

    def test_cache_key_distinguishes_season_year_passes(self):
        s02_2024 = season.source_cache_key("site", "Silo S02", 2024, "TV", 2)
        s03_2026 = season.source_cache_key("site", "Silo S03", 2026, "TV", 3)
        unyear = season.source_cache_key("site", "Silo S03", None, "TV", 3)
        self.assertEqual(3, len({s02_2024, s03_2026, unyear}))

    def test_season_keywords_include_aliases_and_are_bounded(self):
        keywords = season.season_keywords(
            ["权力的游戏前传：龙族", "龙之家族", "House of the Dragon"], 2, limit=6
        )
        self.assertIn("权力的游戏前传：龙族 S02", keywords)
        self.assertIn("权力的游戏前传：龙族 第二季", keywords)
        self.assertIn("龙之家族 S02", keywords)
        self.assertIn("House of the Dragon S02", keywords)
        self.assertLessEqual(len(keywords), 6)

    def test_alias_queries_do_not_repeat_the_same_candidate(self):
        first = SimpleNamespace(
            share_url="https://example.invalid/share/ABC", resource_title="示例剧 S02"
        )
        duplicate = SimpleNamespace(
            share_url="https://example.invalid/share/abc", resource_title="另一显示名"
        )
        second = SimpleNamespace(
            share_url="", resource_title="示例剧 S02 4K", source_title="示例剧"
        )

        result = season.deduplicate_search_hits([first, duplicate, second])

        self.assertEqual([first, second], result)


if __name__ == "__main__":
    unittest.main()
