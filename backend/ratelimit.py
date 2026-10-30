"""
Per-client rate limiting for expensive routes (no external dependencies).

Each research request costs search calls and model tokens, and the server's
API keys are shared by every visitor. A sliding-window limit per client IP
stops one visitor (or a bot) from using up the quota for everyone.

The limiter is in memory, so limits apply per server process. That is
enough for a single instance; a multi-instance deployment would need a
shared store such as Redis.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from backend.config import settings


class SlidingWindowLimiter:
    """Allows at most `limit` hits per `window` seconds for each key."""

    def __init__(self, limit: int, window: float) -> None:
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_prune: float = 0.0

    def hit(self, key: str, now: float | None = None) -> float:
        """
        Record a hit. Returns 0 if allowed, otherwise the seconds to wait.
        A limit of 0 or less disables the limiter.
        """
        if self.limit <= 0:
            return 0.0
        now = time.monotonic() if now is None else now
        self._prune(now)

        hits = self._hits[key]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return hits[0] + self.window - now
        hits.append(now)
        return 0.0

    def _prune(self, now: float) -> None:
        """Forget idle clients now and then, so memory stays bounded."""
        if now - self._last_prune < self.window:
            return
        self._last_prune = now
        for key in [k for k, h in self._hits.items() if not h or h[-1] <= now - self.window]:
            del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()


minute_limiter = SlidingWindowLimiter(settings.rate_limit_per_minute, 60)
hour_limiter = SlidingWindowLimiter(settings.rate_limit_per_hour, 3600)


def client_ip(request: Request) -> str:
    """
    The client's IP. Behind a trusted reverse proxy (TRUST_PROXY=true, or on
    Vercel) the first X-Forwarded-For address is used; otherwise the socket
    address, because the header can be forged by the client.
    """
    if settings.trust_proxy or settings.vercel:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded.split(",")[0].strip():
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def research_rate_limit(request: Request) -> None:
    """FastAPI dependency: reject the request with 429 when the client is over a limit."""
    ip = client_ip(request)
    for limiter, period in ((minute_limiter, "minute"), (hour_limiter, "hour")):
        wait = limiter.hit(ip)
        if wait > 0:
            seconds = math.ceil(wait)
            raise HTTPException(
                status_code=429,
                detail=f"Too many research requests this {period}. Please try again in {_human(seconds)}.",
                headers={"Retry-After": str(seconds)},
            )


def _human(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = math.ceil(seconds / 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"
