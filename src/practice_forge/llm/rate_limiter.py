"""Token bucket per (provider, model) for RPM pacing, plus a persistent
daily request counter (a JSON file, survives process restarts) enforcing
RPD. Free-tier quotas are the binding constraint here (see
config/llm_routing.yaml), not cost — so this is what actually keeps the
pipeline usable across a run, not `llm/client.py`'s cost accounting.

Never silently retries into a wall: once a (provider, model)'s daily quota
is used up, `acquire()` raises `DailyQuotaExhausted` immediately. Callers
must stop cleanly and record resume state, not loop or sleep-until-tomorrow.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from practice_forge.llm.routing import RateLimitConfig

DEFAULT_STATE_PATH = Path(__file__).resolve().parents[3] / "data" / "llm_rate_limit_state.json"


class DailyQuotaExhausted(RuntimeError):
    def __init__(self, provider: str, model: str, rpd: int, used_today: int) -> None:
        self.provider = provider
        self.model = model
        self.rpd = rpd
        self.used_today = used_today
        super().__init__(
            f"{provider}/{model} has used {used_today}/{rpd} requests today (UTC) — "
            "daily quota exhausted. Stopping cleanly rather than retrying into a wall."
        )


def _today_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class _TokenBucket:
    """RPM pacing: at most `rpm` acquisitions per rolling 60s window,
    enforced by sleeping (this is a batch pipeline, not a live server —
    blocking here is fine and simpler than a queue)."""

    def __init__(self, rpm: int) -> None:
        self.rpm = rpm
        self._capacity = float(rpm)
        self._tokens = float(rpm)
        self._refill_per_second = rpm / 60.0
        self._last_refill = time.monotonic()

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_second)
            self._last_refill = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            wait_s = (1.0 - self._tokens) / self._refill_per_second
            time.sleep(min(wait_s, 5.0))


class RateLimiter:
    def __init__(self, state_path: Path = DEFAULT_STATE_PATH) -> None:
        self._state_path = state_path
        self._buckets: dict[tuple[str, str], _TokenBucket] = {}
        self._lock = threading.Lock()

    def _load_state(self) -> dict[str, int]:
        if not self._state_path.exists():
            return {}
        try:
            data: dict[str, int] = json.loads(self._state_path.read_text(encoding="utf-8"))
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_state(self, state: dict[str, int]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")

    def used_today(self, provider: str, model: str) -> int:
        return self._load_state().get(f"{provider}:{model}:{_today_utc()}", 0)

    def acquire(self, provider: str, model: str, config: RateLimitConfig) -> None:
        """Raises `DailyQuotaExhausted` immediately if today's RPD is
        already spent — never sleeps past a daily wall. Otherwise blocks
        briefly if needed to respect RPM, then records the attempt.

        The daily count is incremented for the attempt, not the successful
        response — a network failure after this still consumes a slot.
        That's the conservative direction to be wrong in: it undercounts
        remaining budget rather than overcounts it.
        """
        with self._lock:
            state = self._load_state()
            key = f"{provider}:{model}:{_today_utc()}"
            used = state.get(key, 0)
            if used >= config.rpd:
                raise DailyQuotaExhausted(provider, model, config.rpd, used)
            state[key] = used + 1
            self._save_state(state)

        bucket_key = (provider, model)
        bucket = self._buckets.get(bucket_key)
        if bucket is None or bucket.rpm != config.rpm:
            bucket = _TokenBucket(config.rpm)
            self._buckets[bucket_key] = bucket
        bucket.acquire()
