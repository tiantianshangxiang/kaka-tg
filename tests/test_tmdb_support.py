import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "tmdb_support.py"
spec = importlib.util.spec_from_file_location("tmdb_support", MODULE)
tmdb_support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tmdb_support)


class TmdbSupportTest(unittest.TestCase):
    def test_season_year_map_supports_models_and_dicts(self):
        seasons = [
            SimpleNamespace(season_number=2, air_date="2024-11-14"),
            {"season_number": 3, "air_date": "2026-07-02"},
            {"season_number": 0, "air_date": ""},
        ]

        self.assertEqual({2: 2024, 3: 2026}, tmdb_support.season_year_map(seasons))


if __name__ == "__main__":
    unittest.main()
