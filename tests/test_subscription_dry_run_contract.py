import unittest
from pathlib import Path


class SubscriptionDryRunContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "__init__.py").read_text(encoding="utf-8")
        cls.page = (Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "frontend" / "src" / "components" / "Page.vue").read_text(encoding="utf-8")

    def test_api_uses_shared_read_only_evaluator(self):
        start = self.source.index("def __subscription_dry_run_api")
        end = self.source.index("def __retry_cms_task_api", start)
        body = self.source[start:end]
        self.assertIn("self._evaluate_subscription_candidates(subscribe)", body)
        for forbidden in ("SubscribeOper().update", "_submit_magnet_to_115", "_transfer.transfer", "_cms_client.", "_save_cms_tasks", "post_message"):
            self.assertNotIn(forbidden, body)

    def test_real_process_api_requires_explicit_confirmation_and_queue(self):
        start = self.source.index("def __subscription_process_api")
        end = self.source.index("def __retry_cms_task_api", start)
        body = self.source[start:end]
        self.assertIn('payload.get("confirm") is not True', body)
        self.assertIn("enqueue_subscription(subscribe_id, priority=-5)", body)
        self.assertIn("_forced_process_states", body)
        self.assertIn('original_state not in {"N", "R"}', body)
        self.assertNotIn("SubscribeOper().update", body)
        self.assertNotIn("_submit_magnet_to_115", body)

    def test_evaluator_has_no_action_or_notification_calls(self):
        start = self.source.index("def _evaluate_subscription_candidates")
        end = self.source.index("def _dry_run_summary", start)
        body = self.source[start:end]
        for forbidden in ("SubscribeOper().update", "_submit_magnet_to_115", "_transfer.transfer", "_cms_client.add_magnet", "_save_cms_tasks", "post_message", "_send_fail_notify"):
            self.assertNotIn(forbidden, body)

    def test_page_exposes_explicit_read_only_action(self):
        self.assertIn("开始干跑，不转存", self.page)
        self.assertIn("subscription/dry-run", self.page)
        self.assertIn("只读验证，不转存", self.page)

    def test_vue_detail_page_has_non_empty_host_compatibility_marker(self):
        start = self.source.index("def get_page(self)")
        end = self.source.index("def get_render_mode", start)
        body = self.source[start:end]
        self.assertIn('"component": "VSpacer"', body)
        self.assertNotIn("return []", body)

    def test_dry_run_exposes_year_distribution_and_identity_counts(self):
        self.assertIn('"candidate_year_distribution"', self.source)
        self.assertIn('Counter(', self.source)
        for field in ("year_rejected", "year_deferred", "tmdb_matched", "tmdb_mismatch",
                      "type_mismatch", "season_mismatch", "site_magnets", "site_chinese_1080p",
                      "site_chinese_4k", "safe_candidates"):
            self.assertIn(field, self.source)
            self.assertIn(field, self.page)
        self.assertIn("formatYearDistribution", self.page)
        self.assertIn('"site_search"', self.source)
        self.assertIn("formatSiteYears", self.page)
        self.assertIn("formatSiteHits", self.page)


if __name__ == "__main__":
    unittest.main()
