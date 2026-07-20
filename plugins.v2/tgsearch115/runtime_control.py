# -*- coding: utf-8 -*-
"""Runtime controls for periodic searches, caching, and source protection."""
from __future__ import annotations

import heapq
import itertools
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


def subscription_key(subscribe: Any) -> Tuple[str, str, str, str]:
    """Return a stable media key used to deduplicate one periodic scan."""
    return (
        str(getattr(subscribe, "name", "") or "").strip().casefold(),
        str(getattr(subscribe, "year", "") or "").strip(),
        str(getattr(subscribe, "type", "") or "").strip().upper(),
        str(getattr(subscribe, "season", "") or "").strip(),
    )


def active_unique_subscriptions(subscriptions: Iterable[Any]) -> List[Any]:
    """Keep active MoviePilot subscriptions and deduplicate equivalent media."""
    result: List[Any] = []
    seen = set()
    for subscribe in subscriptions or []:
        if str(getattr(subscribe, "state", "N") or "N").upper() != "N":
            continue
        sid = getattr(subscribe, "id", None)
        key = subscription_key(subscribe)
        if not sid or not key[0] or key in seen:
            continue
        seen.add(key)
        result.append(subscribe)
    return result


class TtlCache:
    """Small thread-safe in-memory cache used to avoid repeated source searches."""

    def __init__(self, ttl_seconds: int = 7200, max_entries: int = 256,
                 clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = max(60, int(ttl_seconds))
        self.max_entries = max(16, int(max_entries))
        self._clock = clock
        self._items: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Optional[Any]:
        now = self._clock()
        with self._lock:
            item = self._items.get(key)
            if not item:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            return value

    def set(self, key: Any, value: Any) -> None:
        now = self._clock()
        with self._lock:
            expired = [k for k, (expires_at, _) in self._items.items()
                       if expires_at <= now]
            for old_key in expired:
                self._items.pop(old_key, None)
            if len(self._items) >= self.max_entries:
                oldest_key = min(self._items, key=lambda k: self._items[k][0])
                self._items.pop(oldest_key, None)
            self._items[key] = (now + self.ttl_seconds, value)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class SourceCircuitBreaker:
    """Open a source circuit after consecutive throttle or transport failures."""

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 3600,
                 clock: Callable[[], float] = time.time):
        self.failure_threshold = max(1, int(failure_threshold))
        self.cooldown_seconds = max(60, int(cooldown_seconds))
        self._clock = clock
        self._states: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def allow(self, source: str) -> Tuple[bool, int]:
        now = self._clock()
        with self._lock:
            state = self._states.get(source) or {}
            open_until = float(state.get("open_until") or 0)
            if open_until > now:
                return False, max(1, int(open_until - now))
            if open_until:
                state.update({"failures": 0, "open_until": 0, "reason": ""})
                self._states[source] = state
            return True, 0

    def success(self, source: str) -> None:
        with self._lock:
            self._states[source] = {
                "failures": 0, "open_until": 0, "reason": "", "updated_at": self._clock()
            }

    def failure(self, source: str, reason: str) -> bool:
        now = self._clock()
        with self._lock:
            state = self._states.setdefault(source, {
                "failures": 0, "open_until": 0, "reason": "", "updated_at": now
            })
            state["failures"] = int(state.get("failures") or 0) + 1
            state["reason"] = str(reason or "source failure")[:160]
            state["updated_at"] = now
            if state["failures"] >= self.failure_threshold:
                state["open_until"] = now + self.cooldown_seconds
                return True
            return False

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        now = self._clock()
        with self._lock:
            return {
                source: {
                    "failures": int(state.get("failures") or 0),
                    "cooldown_seconds": max(0, int(float(state.get("open_until") or 0) - now)),
                    "reason": state.get("reason") or "",
                }
                for source, state in self._states.items()
            }


class SearchCoordinator:
    """Single bounded priority queue plus a stoppable periodic producer."""

    def __init__(
        self,
        process_subscription: Callable[[int], Any],
        list_subscriptions: Callable[[], Iterable[Any]],
        interval_hours: int = 2,
        jitter_minutes: int = 10,
        between_items: Tuple[float, float] = (5.0, 10.0),
        queue_size: int = 100,
        periodic_enabled: bool = True,
        random_uniform: Callable[[float, float], float] = random.uniform,
    ):
        self.process_subscription = process_subscription
        self.list_subscriptions = list_subscriptions
        self.interval_hours = min(3, max(1, int(interval_hours or 2)))
        self.jitter_minutes = min(10, max(0, int(jitter_minutes or 0)))
        low, high = between_items
        normalized_low = max(0.0, float(low))
        self.between_items = (normalized_low, max(normalized_low, float(high)))
        self.queue_size = max(10, int(queue_size))
        self.periodic_enabled = bool(periodic_enabled)
        self._random_uniform = random_uniform
        self._condition = threading.Condition()
        self._heap: List[Tuple[int, int, Dict[str, Any]]] = []
        self._sequence = itertools.count()
        self._pending_ids = set()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._scheduler: Optional[threading.Thread] = None
        self._stats_lock = threading.Lock()
        self._last_run = ""
        self._next_run = ""
        self._scanned_count = 0
        self._running_id: Optional[int] = None

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._worker_loop,
                                        name="tg115-search-worker", daemon=True)
        self._scheduler = threading.Thread(target=self._scheduler_loop,
                                           name="tg115-search-scheduler", daemon=True) \
            if self.periodic_enabled else None
        self._worker.start()
        if self._scheduler:
            self._scheduler.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        for thread in (self._scheduler, self._worker):
            if thread and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=timeout)
        self._scheduler = None
        self._worker = None
        with self._condition:
            for _priority, _sequence, job in self._heap:
                if job.get("kind") == "manual":
                    job["error"] = RuntimeError("插件正在停止，搜索任务已取消")
                    job["done"].set()
            self._heap.clear()
            self._pending_ids.clear()

    def enqueue_subscription(self, subscribe_id: int, priority: int = 10) -> bool:
        sid = int(subscribe_id)
        with self._condition:
            if self._stop.is_set() or sid in self._pending_ids or len(self._heap) >= self.queue_size:
                return False
            job = {"kind": "subscription", "subscribe_id": sid}
            heapq.heappush(self._heap, (int(priority), next(self._sequence), job))
            self._pending_ids.add(sid)
            self._condition.notify()
            return True

    def submit_manual(self, callback: Callable[[], Any], timeout: float = 300.0) -> Any:
        done = threading.Event()
        job = {"kind": "manual", "callback": callback, "done": done,
               "result": None, "error": None}
        with self._condition:
            if self._stop.is_set() or len(self._heap) >= self.queue_size:
                raise RuntimeError("搜索队列不可用或已满")
            heapq.heappush(self._heap, (-10, next(self._sequence), job))
            self._condition.notify()
        if not done.wait(timeout=max(1.0, float(timeout))):
            raise TimeoutError("手动搜索等待队列超时")
        if job["error"]:
            raise job["error"]
        return job["result"]

    def scan_now(self) -> int:
        subscriptions = active_unique_subscriptions(self.list_subscriptions() or [])
        enqueued = 0
        for subscribe in subscriptions:
            if self.enqueue_subscription(int(subscribe.id), priority=10):
                enqueued += 1
        with self._stats_lock:
            self._last_run = datetime.now().astimezone().isoformat(timespec="seconds")
            self._scanned_count = len(subscriptions)
        return enqueued

    def status(self) -> Dict[str, Any]:
        with self._condition:
            queued = len(self._heap)
        with self._stats_lock:
            return {
                "running": bool(self._worker and self._worker.is_alive()),
                "last_run": self._last_run,
                "next_run": self._next_run,
                "scanned_count": self._scanned_count,
                "queue_size": queued,
                "running_subscribe_id": self._running_id,
            }

    def _scheduler_loop(self) -> None:
        while not self._stop.is_set():
            delay = self._random_uniform(0, self.jitter_minutes * 60)
            next_run = datetime.now().astimezone() + timedelta(seconds=delay)
            with self._stats_lock:
                self._next_run = next_run.isoformat(timespec="seconds")
            if self._stop.wait(delay):
                break
            try:
                self.scan_now()
            except Exception:
                # The plugin callback logs database errors; keep the scheduler alive.
                pass
            interval = self.interval_hours * 3600
            next_run = datetime.now().astimezone() + timedelta(seconds=interval)
            with self._stats_lock:
                self._next_run = next_run.isoformat(timespec="seconds")
            if self._stop.wait(interval):
                break

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            with self._condition:
                while not self._heap and not self._stop.is_set():
                    self._condition.wait(timeout=1.0)
                if self._stop.is_set():
                    break
                _priority, _sequence, job = heapq.heappop(self._heap)
            if job["kind"] == "manual":
                try:
                    job["result"] = job["callback"]()
                except Exception as exc:
                    job["error"] = exc
                finally:
                    job["done"].set()
                continue

            sid = int(job["subscribe_id"])
            with self._stats_lock:
                self._running_id = sid
            try:
                self.process_subscription(sid)
            finally:
                with self._condition:
                    self._pending_ids.discard(sid)
                with self._stats_lock:
                    self._running_id = None
            delay = self._random_uniform(*self.between_items)
            if self._stop.wait(delay):
                break
