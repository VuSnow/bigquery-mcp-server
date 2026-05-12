"""Tests for RateLimiter — sliding window rate limiting."""
import time
from unittest.mock import patch

import pytest

from bigquery_mcp.services.bigquery.guardrails.rate_limiter import RateLimiter


class TestRateLimiterBasic:
    """Test basic rate limiting behavior."""

    def test_allows_first_call(self):
        limiter = RateLimiter(max_calls=10, window_seconds=60)
        result = limiter.check_and_reserve()
        assert result["allowed"] is True
        assert result["remaining"] == 9

    def test_allows_within_limit(self):
        limiter = RateLimiter(max_calls=5, window_seconds=60)
        for _ in range(5):
            limiter.check_and_reserve()
        # 5 calls reserved, all used up
        result = limiter.check_and_reserve()
        assert result["allowed"] is False

    def test_blocks_over_limit(self):
        limiter = RateLimiter(max_calls=3, window_seconds=60)
        for _ in range(3):
            limiter.check_and_reserve()
        result = limiter.check_and_reserve()
        assert result["allowed"] is False
        assert result["remaining"] == 0
        assert "reset_in_seconds" in result

    def test_remaining_decreases(self):
        limiter = RateLimiter(max_calls=5, window_seconds=60)
        result = limiter.check_and_reserve()
        assert result["remaining"] == 4

        result = limiter.check_and_reserve()
        assert result["remaining"] == 3


class TestRateLimiterSlidingWindow:
    """Test sliding window expiration."""

    def test_expired_calls_cleaned(self):
        limiter = RateLimiter(max_calls=2, window_seconds=1)
        limiter.check_and_reserve()
        limiter.check_and_reserve()

        # All slots used
        assert limiter.check_and_reserve()["allowed"] is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again after window expires
        result = limiter.check_and_reserve()
        assert result["allowed"] is True
        assert result["remaining"] == 1


class TestRateLimiterStatus:
    """Test status reporting."""

    def test_status_empty(self):
        limiter = RateLimiter(max_calls=100, window_seconds=3600)
        status = limiter.get_status()
        assert status["calls_used"] == 0
        assert status["remaining"] == 100
        assert status["limit"] == 100
        assert status["window_seconds"] == 3600

    def test_status_after_calls(self):
        limiter = RateLimiter(max_calls=10, window_seconds=60)
        for _ in range(3):
            limiter.check_and_reserve()
        status = limiter.get_status()
        assert status["calls_used"] == 3
        assert status["remaining"] == 7

    def test_properties(self):
        limiter = RateLimiter(max_calls=50, window_seconds=120)
        assert limiter.max_calls == 50
        assert limiter.window_seconds == 120


class TestRateLimiterConcurrency:
    """Test thread safety under concurrent access."""

    def test_thread_safe_under_concurrent_load(self):
        """20 concurrent calls with limit=10 should allow exactly 10."""
        import threading

        limiter = RateLimiter(max_calls=10, window_seconds=3600)
        results = []
        lock = threading.Lock()

        def worker():
            for _ in range(5):
                r = limiter.check_and_reserve()
                with lock:
                    results.append(r["allowed"])

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed_count = sum(1 for r in results if r)
        denied_count = sum(1 for r in results if not r)
        assert allowed_count == 10
        assert denied_count == 10
