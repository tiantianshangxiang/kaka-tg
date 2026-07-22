import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


PACKAGE_DIR = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115"
package = sys.modules.setdefault("tgsearch115", types.ModuleType("tgsearch115"))
package.__path__ = [str(PACKAGE_DIR)]
media_spec = importlib.util.spec_from_file_location("tgsearch115.media_types", PACKAGE_DIR / "media_types.py")
media_types = importlib.util.module_from_spec(media_spec)
sys.modules[media_spec.name] = media_types
media_spec.loader.exec_module(media_types)
spec = importlib.util.spec_from_file_location("tgsearch115.site_query_policy", PACKAGE_DIR / "site_query_policy.py")
policy = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = policy
spec.loader.exec_module(policy)


class SiteQueryPolicyTest(unittest.TestCase):
    def test_s02_uses_series_season_and_no_year(self):
        subscribe = SimpleNamespace(type="TV", year=2023)
        media = SimpleNamespace(type="TV", season_years={2: 2024, 3: 2026})
        self.assertEqual([2023, 2024, None], policy.site_query_years(subscribe, media, 2))

    def test_s03_uses_distinct_season_year_and_no_year(self):
        subscribe = SimpleNamespace(type="TV", year=2023)
        media = SimpleNamespace(type="TV", season_years={2: 2024, 3: 2026})
        self.assertEqual([2023, 2026, None], policy.site_query_years(subscribe, media, 3))

    def test_movie_stays_strict_to_subscription_year(self):
        subscribe = SimpleNamespace(type="MOVIE", year=2023)
        media = SimpleNamespace(type="MOVIE", season_years={})
        self.assertEqual([2023], policy.site_query_years(subscribe, media, None))


if __name__ == "__main__":
    unittest.main()
