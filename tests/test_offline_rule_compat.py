import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "plugins.v2"
    / "tgsearch115"
    / "offline_rule_compat.py"
)
spec = importlib.util.spec_from_file_location("tgsearch115_offline_rule_compat", MODULE_PATH)
compat = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compat
spec.loader.exec_module(compat)


def _share(title="示例剧 S02 1080P 中文字幕", description=""):
    return SimpleNamespace(
        title=title,
        description=description or title,
        labels=[],
        size=0,
        seeders=0,
        downloadvolumefactor=None,
        _tg115_unavailable_rule_fields={
            "size", "seeders", "downloadvolumefactor", "publish_time",
        },
    )


class OfflineRuleCompatibilityTest(unittest.TestCase):
    def test_missing_tracker_metadata_does_not_reject_semantically_valid_share(self):
        candidate = _share()
        groups = [{"name": "1080", "rule_string": "CNSUB & 1080P & BIG & FREE & NEW"}]
        rules = {
            "CNSUB": {"include": ["中字|中文字幕"]},
            "1080P": {"include": ["1080P"]},
            "BIG": {"size_range": ">500"},
            "FREE": {"downloadvolumefactor": 0},
            "NEW": {"publish_time": "0-1440"},
        }

        matched, diagnostics = compat.filter_offline_share_rules(
            [candidate], groups, rules, SimpleNamespace()
        )

        self.assertEqual([candidate], matched)
        self.assertEqual({"size", "downloadvolumefactor", "publish_time"}, diagnostics.skipped_fields)

    def test_observable_title_rule_still_rejects_share(self):
        candidate = _share(title="示例剧 S02 720P English")
        groups = [{"name": "1080", "rule_string": "CNSUB & 1080P"}]
        rules = {
            "CNSUB": {"include": ["中字|中文字幕"]},
            "1080P": {"include": ["1080P"]},
        }

        matched, diagnostics = compat.filter_offline_share_rules(
            [candidate], groups, rules, SimpleNamespace()
        )

        self.assertEqual([], matched)
        self.assertEqual(1, diagnostics.rejected_by_semantic_rule)

    def test_boolean_and_priority_expression_keep_moviepilot_semantics(self):
        candidate = _share(title="示例剧 S02 4K 中文字幕")
        groups = [{"name": "priority", "rule_string": "1080P & CNSUB > 4K & CNSUB"}]
        rules = {
            "1080P": {"include": ["1080P"]},
            "4K": {"include": ["4K"]},
            "CNSUB": {"include": ["中字|中文字幕"]},
        }

        matched, _diagnostics = compat.filter_offline_share_rules(
            [candidate], groups, rules, SimpleNamespace()
        )

        self.assertEqual([candidate], matched)
        self.assertEqual(99, candidate.pri_order)

    def test_invalid_rule_expression_fails_closed(self):
        candidate = _share()
        matched, diagnostics = compat.filter_offline_share_rules(
            [candidate], [{"rule_string": "CNSUB &"}], {"CNSUB": {}}, SimpleNamespace()
        )

        self.assertEqual([], matched)
        self.assertEqual(1, diagnostics.parse_errors)

    def test_invalid_rule_character_fails_closed(self):
        candidate = _share()
        matched, diagnostics = compat.filter_offline_share_rules(
            [candidate], [{"rule_string": "CNSUB @ 1080P"}], {"CNSUB": {}, "1080P": {}}, SimpleNamespace()
        )

        self.assertEqual([], matched)
        self.assertEqual(1, diagnostics.parse_errors)


if __name__ == "__main__":
    unittest.main()
