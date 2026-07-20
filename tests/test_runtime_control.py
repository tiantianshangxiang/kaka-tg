import importlib.util
import sys
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins.v2" / "tgsearch115" / "runtime_control.py"
spec = importlib.util.spec_from_file_location("tgsearch115_runtime_control", MODULE_PATH)
runtime_control = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runtime_control
spec.loader.exec_module(runtime_control)


class RuntimeControlTest(unittest.TestCase):
    def test_active_subscriptions_are_filtered_and_deduplicated(self):
        subscriptions = [
            SimpleNamespace(id=1, state="N", name="示例", year=2026, type="MOVIE", season=None),
            SimpleNamespace(id=2, state="N", name="示例", year=2026, type="MOVIE", season=None),
            SimpleNamespace(id=3, state="P", name="暂停", year=2026, type="MOVIE", season=None),
        ]

        result = runtime_control.active_unique_subscriptions(subscriptions)

        self.assertEqual([1], [item.id for item in result])

    def test_ttl_cache_expires(self):
        now = [100.0]
        cache = runtime_control.TtlCache(ttl_seconds=60, clock=lambda: now[0])
        cache.set("key", [1])
        self.assertEqual([1], cache.get("key"))
        now[0] += 61
        self.assertIsNone(cache.get("key"))

    def test_circuit_breaker_opens_and_recovers(self):
        now = [100.0]
        breaker = runtime_control.SourceCircuitBreaker(
            failure_threshold=2, cooldown_seconds=60, clock=lambda: now[0]
        )
        self.assertFalse(breaker.failure("site", "HTTP 403"))
        self.assertTrue(breaker.failure("site", "HTTP 403"))
        self.assertEqual((False, 60), breaker.allow("site"))
        now[0] += 61
        self.assertEqual((True, 0), breaker.allow("site"))

    def test_manual_job_has_priority_and_stop_joins_threads(self):
        order = []
        coordinator = runtime_control.SearchCoordinator(
            process_subscription=lambda sid: order.append(f"sub:{sid}"),
            list_subscriptions=lambda: [],
            periodic_enabled=False,
            between_items=(0, 0),
        )
        self.assertTrue(coordinator.enqueue_subscription(7, priority=10))
        result = {}

        def submit_manual():
            result["value"] = coordinator.submit_manual(
                lambda: order.append("manual") or "ok", timeout=2
            )

        waiter = threading.Thread(target=submit_manual)
        waiter.start()
        for _ in range(50):
            if coordinator.status()["queue_size"] == 2:
                break
            time.sleep(0.01)
        coordinator.start()
        waiter.join(timeout=2)
        for _ in range(50):
            if "sub:7" in order:
                break
            time.sleep(0.01)
        coordinator.stop()

        self.assertEqual("ok", result.get("value"))
        self.assertEqual(["manual", "sub:7"], order)
        active_names = {thread.name for thread in threading.enumerate()}
        self.assertNotIn("tg115-search-worker", active_names)
        self.assertNotIn("tg115-search-scheduler", active_names)

    def test_stop_cancels_queued_manual_request(self):
        coordinator = runtime_control.SearchCoordinator(
            process_subscription=lambda _sid: None,
            list_subscriptions=lambda: [],
            periodic_enabled=False,
        )
        result = {}

        def submit_manual():
            try:
                coordinator.submit_manual(lambda: "unexpected", timeout=2)
            except Exception as exc:
                result["error"] = str(exc)

        waiter = threading.Thread(target=submit_manual)
        waiter.start()
        for _ in range(50):
            if coordinator.status()["queue_size"] == 1:
                break
            time.sleep(0.01)
        coordinator.stop()
        waiter.join(timeout=2)

        self.assertIn("已取消", result.get("error", ""))


if __name__ == "__main__":
    unittest.main()
