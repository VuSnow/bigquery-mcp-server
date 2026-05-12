"""Rate limiter — sliding window per-client rate limiting."""
from __future__ import annotations

import time
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding window rate limiter. Tracks calls per time window."""

    def __init__(self, max_calls: int = 100, window_seconds: int = 3600) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._timestamps: list[float] = []

    @property
    def max_calls(self) -> int:
        return self._max_calls

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def _cleanup(self) -> None:
        """Remove timestamps outside the current window."""
        cutoff = time.time() - self._window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    def check(self) -> Dict[str, object]:
        """Check if a call is allowed under the rate limit.

        Returns:
            Dict with allowed (bool), remaining calls, and reset info.
        """
        self._cleanup()

        remaining = self._max_calls - len(self._timestamps)

        if remaining <= 0:
            oldest = min(self._timestamps) if self._timestamps else time.time()
            reset_in = int(oldest + self._window_seconds - time.time())
            logger.warning(
                "[rate_limit] Rate limit exceeded. %d calls in %ds window. Reset in %ds.",
                len(self._timestamps), self._window_seconds, reset_in,
            )
            return {
                "allowed": False,
                "remaining": 0,
                "reset_in_seconds": max(0, reset_in),
                "limit": self._max_calls,
                "window_seconds": self._window_seconds,
            }

        return {
            "allowed": True,
            "remaining": remaining,
            "limit": self._max_calls,
            "window_seconds": self._window_seconds,
        }

    def record(self) -> None:
        """Record a successful call."""
        self._timestamps.append(time.time())

    def get_status(self) -> Dict[str, object]:
        """Get current rate limit status without recording a call."""
        self._cleanup()
        remaining = self._max_calls - len(self._timestamps)
        return {
            "calls_used": len(self._timestamps),
            "remaining": max(0, remaining),
            "limit": self._max_calls,
            "window_seconds": self._window_seconds,
        }
