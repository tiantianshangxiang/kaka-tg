import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


class _Logger:
    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: None


class _FakeMeta:
    def __init__(self, title):
        self.title = title
        self.season_list = [3] if "S03" in title else ([2] if "S02" in title else [])
        self.begin_season = self.season_list[0] if self.season_list else None


class _FakeMediaChain:
    candidate_media = None
    calls = 0

    def recognize_by_meta(self, _meta, episode_group=None, obtain_images=False):
        type(self).calls += 1
        return type(self).candidate_media


class _FakeTorrentHelper:
    @staticmethod
    def match_torrent(mediainfo, torrent_meta, torrent):
        if getattr(torrent, "match_error", None):
            raise torrent.match_error
        return bool(getattr(torrent, "local_match", False))


def _install_module(name, **attrs):
    module = sys.modules.setdefault(name, types.ModuleType(name))
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


_install_module("app")
_install_module("app.chain")
_install_module("app.chain.media", MediaChain=_FakeMediaChain)
_install_module("app.core")
_install_module("app.core.metainfo", MetaInfo=lambda title, subtitle=None: _FakeMeta(title))
_install_module("app.helper")
_install_module("app.helper.torrent", TorrentHelper=_FakeTorrentHelper)
_install_module("app.log", logger=_Logger())

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins.v2"
    / "tgsearch115"
    / "identity_matcher.py"
)
PACKAGE_DIR = MODULE_PATH.parent
package = sys.modules.setdefault("tgsearch115", types.ModuleType("tgsearch115"))
package.__path__ = [str(PACKAGE_DIR)]
media_type_spec = importlib.util.spec_from_file_location(
    "tgsearch115.media_types", PACKAGE_DIR / "media_types.py"
)
media_type_module = importlib.util.module_from_spec(media_type_spec)
sys.modules[media_type_spec.name] = media_type_module
media_type_spec.loader.exec_module(media_type_module)
season_spec = importlib.util.spec_from_file_location(
    "tgsearch115.season_support", PACKAGE_DIR / "season_support.py"
)
season_module = importlib.util.module_from_spec(season_spec)
sys.modules[season_spec.name] = season_module
season_spec.loader.exec_module(season_module)
spec = importlib.util.spec_from_file_location("tgsearch115.identity_matcher", MODULE_PATH)
identity_matcher = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = identity_matcher
spec.loader.exec_module(identity_matcher)


def _torrent(title="示例电影 (2026)", local_match=True):
    return SimpleNamespace(
        title=title,
        description=title,
        local_match=local_match,
        _tg115_identity_title=title,
    )


class IdentityMatcherTest(unittest.TestCase):
    def setUp(self):
        _FakeMediaChain.calls = 0
        _FakeMediaChain.candidate_media = None

    def test_confirms_same_tmdb_id(self):
        target = SimpleNamespace(type="电影", tmdb_id=100, douban_id=None, season=None)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=None, episode_group=None)
        _FakeMediaChain.candidate_media = SimpleNamespace(
            type="电影", tmdb_id=100, douban_id=None
        )

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent()
        )

        self.assertTrue(result.confirmed)
        self.assertEqual("tmdb_id", result.match_source)

    def test_rejects_different_tmdb_id(self):
        target = SimpleNamespace(type="电影", tmdb_id=100, douban_id=None, season=None)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=None, episode_group=None)
        _FakeMediaChain.candidate_media = SimpleNamespace(
            type="电影", tmdb_id=200, douban_id=None
        )

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent()
        )

        self.assertFalse(result.confirmed)
        self.assertIn("TMDB ID 不匹配", result.reason)

    def test_local_mismatch_does_not_call_media_chain(self):
        target = SimpleNamespace(type="电影", tmdb_id=100, douban_id=None, season=None)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=None, episode_group=None)

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent(local_match=False)
        )

        self.assertFalse(result.confirmed)
        self.assertEqual(0, _FakeMediaChain.calls)

    def test_missing_target_ids_does_not_call_media_chain(self):
        target = SimpleNamespace(type="电影", tmdb_id=None, douban_id=None, season=None)
        subscribe = SimpleNamespace(tmdbid=None, doubanid=None, season=None, episode_group=None)

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent(local_match=True)
        )

        self.assertFalse(result.confirmed)
        self.assertIn("缺少 TMDB/豆瓣 ID", result.reason)
        self.assertEqual(0, _FakeMediaChain.calls)

    def test_rejects_wrong_tv_season_before_recognition(self):
        target = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None, season=1)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=1, episode_group=None)

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent(title="示例剧 S02", local_match=True)
        )

        self.assertFalse(result.confirmed)
        self.assertIn("季号不匹配", result.reason)
        self.assertEqual(0, _FakeMediaChain.calls)

    def test_read_only_share_metadata_can_reach_exact_tmdb_confirmation(self):
        target = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None, season=2)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=2, episode_group=None)
        torrent = _torrent(title="Silo.S02.2024.1080p.CHINESE", local_match=False)
        torrent._tg115_metadata_verified = True
        _FakeMediaChain.candidate_media = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None)

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertTrue(result.confirmed)
        self.assertEqual("tmdb_id", result.match_source)

    def test_rejects_missing_tv_season_before_recognition(self):
        target = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None, season=2)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=2, episode_group=None)

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent(title="示例剧 1080P", local_match=True)
        )

        self.assertFalse(result.confirmed)
        self.assertIn("无明确季号", result.reason)
        self.assertEqual(0, _FakeMediaChain.calls)

    def test_multi_season_collection_can_match_target_season(self):
        target = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None, season=2)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=2, episode_group=None)
        candidate = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None)
        calls = []

        result = identity_matcher.confirm_candidate_identity(
            subscribe,
            target,
            _torrent(title="示例剧 S01-S03", local_match=True),
            recognize_candidate=lambda _meta, _group: calls.append(1) or candidate,
        )

        self.assertTrue(result.confirmed)
        self.assertEqual([1], calls)

    def test_recognition_unavailable_does_not_confirm_candidate(self):
        target = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None, season=2)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=2, episode_group=None)

        def unavailable(_meta, _group):
            raise RuntimeError("identity_unavailable")

        result = identity_matcher.confirm_candidate_identity(
            subscribe,
            target,
            _torrent(title="示例剧 S02", local_match=True),
            recognize_candidate=unavailable,
        )

        self.assertFalse(result.confirmed)
        self.assertEqual("identity_unavailable", result.match_source)
        self.assertTrue(result.recognition_attempted)

    def test_type_value_attribute_error_is_reported_as_compatibility_failure(self):
        target = SimpleNamespace(type="电视剧", tmdb_id=100, douban_id=None, season=2)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=2, episode_group=None)
        torrent = _torrent(title="示例剧 S02", local_match=True)
        torrent.match_error = AttributeError("'str' object has no attribute 'value'")

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertFalse(result.confirmed)
        self.assertIn("媒体类型兼容错误", result.reason)

    def test_tv_season_year_can_differ_from_series_year_after_exact_tmdb_confirmation(self):
        target = SimpleNamespace(
            type="TV", tmdb_id=100, douban_id=None, season=3, year=2023,
            season_years={3: 2026},
        )
        subscribe = SimpleNamespace(
            tmdbid=100, doubanid=None, season=3, year=2023, episode_group=None,
        )
        torrent = _torrent(title="Silo.S03.2026.2160p.CHINESE", local_match=False)
        torrent._tg115_metadata_verified = True
        _FakeMediaChain.candidate_media = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None)

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertTrue(result.confirmed)
        self.assertEqual("tv_season_year_match", result.year_policy)
        self.assertEqual("share_metadata_tmdb_fallback", result.identity_path)
        self.assertEqual(2026, result.candidate_year)
        self.assertEqual(2026, result.target_season_year)

    def test_tv_year_difference_without_season_year_is_deferred_to_exact_tmdb(self):
        target = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None, season=3, year=2023)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=3, year=2023, episode_group=None)
        torrent = _torrent(title="Silo.S03.2026.1080p.CHINESE", local_match=False)
        torrent._tg115_metadata_verified = True
        _FakeMediaChain.candidate_media = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None)

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertTrue(result.confirmed)
        self.assertEqual("tv_year_deferred_to_tmdb", result.year_policy)

    def test_tmdb_search_fallback_selects_exact_id_from_multiple_results(self):
        target = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None, season=3, year=2023)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=3, year=2023, episode_group=None)
        torrent = _torrent(title="Silo.S03.2026.1080p.CHINESE", local_match=False)
        torrent._tg115_metadata_verified = True
        wrong = SimpleNamespace(type="TV", tmdb_id=200, douban_id=None)
        exact = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None)

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, torrent,
            recognize_candidate=lambda _meta, _group: [wrong, exact],
        )

        self.assertTrue(result.confirmed)
        self.assertEqual("tmdb_id", result.match_source)

    def test_tv_year_difference_still_rejects_wrong_tmdb_id(self):
        target = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None, season=3, year=2023)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=3, year=2023, episode_group=None)
        torrent = _torrent(title="Silo.S03.2026.1080p.CHINESE", local_match=False)
        torrent._tg115_metadata_verified = True
        _FakeMediaChain.candidate_media = SimpleNamespace(type="TV", tmdb_id=200, douban_id=None)

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertFalse(result.confirmed)
        self.assertIn("TMDB ID 不匹配", result.reason)

    def test_tv_year_difference_still_rejects_wrong_type(self):
        target = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None, season=3, year=2023)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=3, year=2023, episode_group=None)
        torrent = _torrent(title="Silo.S03.2026.1080p.CHINESE", local_match=False)
        torrent._tg115_metadata_verified = True
        _FakeMediaChain.candidate_media = SimpleNamespace(type="MOVIE", tmdb_id=100, douban_id=None)

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertFalse(result.confirmed)
        self.assertIn("媒体类型", result.reason)

    def test_tv_year_difference_rejects_wrong_target_season_before_recognition(self):
        target = SimpleNamespace(type="TV", tmdb_id=100, douban_id=None, season=3, year=2023)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=3, year=2023, episode_group=None)
        torrent = _torrent(title="Silo.S02.2026.1080p.CHINESE", local_match=True)

        result = identity_matcher.confirm_candidate_identity(subscribe, target, torrent)

        self.assertFalse(result.confirmed)
        self.assertIn("季号不匹配", result.reason)
        self.assertEqual(0, _FakeMediaChain.calls)

    def test_movie_year_conflict_is_rejected_before_recognition(self):
        target = SimpleNamespace(type="MOVIE", tmdb_id=100, douban_id=None, season=None, year=2023)
        subscribe = SimpleNamespace(tmdbid=100, doubanid=None, season=None, year=2023, episode_group=None)

        result = identity_matcher.confirm_candidate_identity(
            subscribe, target, _torrent(title="Example.2026.1080p", local_match=True)
        )

        self.assertFalse(result.confirmed)
        self.assertEqual("year_conflict_rejected", result.year_policy)
        self.assertEqual(0, _FakeMediaChain.calls)


if __name__ == "__main__":
    unittest.main()
