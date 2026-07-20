import importlib.util
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "cms_tasks.py"
spec = importlib.util.spec_from_file_location("tgsearch115_cms_tasks", MODULE_PATH)
cms_tasks = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cms_tasks
spec.loader.exec_module(cms_tasks)


def magnet(char="a"):
    return "magnet:?xt=urn:btih:" + char * 40


class CmsTaskLedgerTest(unittest.TestCase):
    def test_active_btih_is_deduplicated_across_reload(self):
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        ledger = cms_tasks.CmsTaskLedger(now=lambda: now)
        subscribe = SimpleNamespace(
            id=8, tmdbid=100, doubanid=None, type="MOVIE", season=None
        )
        first = ledger.add(magnet(), "示例电影", subscribe=subscribe)
        restored = cms_tasks.CmsTaskLedger(ledger.records, now=lambda: now)

        self.assertEqual(first["btih"], restored.active_by_btih("a" * 40)["btih"])
        self.assertNotIn("magnet", restored.public_records()[0])

    def test_btih_reservation_is_atomic(self):
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        ledger = cms_tasks.CmsTaskLedger(now=lambda: now)

        first, first_created = ledger.reserve(magnet(), "示例电影")
        second, second_created = ledger.reserve(magnet(), "重复任务")

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertIs(first, second)
        self.assertEqual(1, len(ledger.records))

    def test_cms_acceptance_does_not_complete_subscription(self):
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        ledger = cms_tasks.CmsTaskLedger(now=lambda: now)
        ledger.add(magnet(), "示例电影", subscribe=SimpleNamespace(
            id=8, tmdbid=100, doubanid=None, type="MOVIE", season=None
        ))

        result = ledger.reconcile(
            timeout_hours=12,
            subscription_exists=lambda _sid: True,
            history_exists=lambda _record: False,
            restore_subscription=lambda _sid: self.fail("should not restore"),
        )

        self.assertEqual({"completed": 0, "failed": 0, "timed_out": 0}, result)
        self.assertEqual("downloading", ledger.records[0]["status"])

    def test_timeout_restores_subscription(self):
        now = [datetime(2026, 7, 20, tzinfo=timezone.utc)]
        ledger = cms_tasks.CmsTaskLedger(now=lambda: now[0])
        ledger.add(magnet(), "示例电影", subscribe=SimpleNamespace(
            id=8, tmdbid=100, doubanid=None, type="MOVIE", season=None
        ))
        now[0] += timedelta(hours=13)
        restored = []

        result = ledger.reconcile(
            timeout_hours=12,
            subscription_exists=lambda _sid: True,
            history_exists=lambda _record: False,
            restore_subscription=restored.append,
        )

        self.assertEqual(1, result["timed_out"])
        self.assertEqual([8], restored)
        self.assertEqual("timed_out", ledger.records[0]["status"])

    def test_moviepilot_history_marks_task_completed(self):
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        ledger = cms_tasks.CmsTaskLedger(now=lambda: now)
        ledger.add(magnet(), "示例电影", subscribe=SimpleNamespace(
            id=8, tmdbid=100, doubanid=None, type="MOVIE", season=None
        ))

        result = ledger.reconcile(
            timeout_hours=12,
            subscription_exists=lambda _sid: True,
            history_exists=lambda _record: True,
            restore_subscription=lambda _sid: None,
        )

        self.assertEqual(1, result["completed"])
        self.assertEqual("completed", ledger.records[0]["status"])

    def test_missing_subscription_without_history_is_not_completed(self):
        now = datetime(2026, 7, 20, tzinfo=timezone.utc)
        ledger = cms_tasks.CmsTaskLedger(now=lambda: now)
        ledger.add(magnet(), "示例电影", subscribe=SimpleNamespace(
            id=8, tmdbid=100, doubanid=None, type="MOVIE", season=None
        ))

        result = ledger.reconcile(
            timeout_hours=12,
            subscription_exists=lambda _sid: False,
            history_exists=lambda _record: False,
            restore_subscription=lambda _sid: None,
        )

        self.assertEqual(1, result["failed"])
        self.assertEqual("failed", ledger.records[0]["status"])


if __name__ == "__main__":
    unittest.main()
