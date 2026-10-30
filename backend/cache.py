"""
Small in-memory caches with time-based expiry (no external dependencies).

Used to remember the sources gathered for a topic, so researching the same
topic again within the TTL skips planning, searching and page reading.
Each server process has its own cache; it is cleared on restart.
"""

from __future__ import annotations

import copy
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """A least-recently-used cache whose entries expire after `ttl` seconds."""

    def __init__(self, ttl: float, max_entries: int = 100) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if time.monotonic() >= expires:
            del self._data[key]
            return None
        self._data.move_to_end(key)
        return copy.deepcopy(value)   # callers may mutate what they get back

    def set(self, key: str, value: Any) -> None:
        if self.ttl <= 0:
            return
        self._data[key] = (time.monotonic() + self.ttl, copy.deepcopy(value))
        self._data.move_to_end(key)
        while len(self._data) > self.max_entries:
            self._data.popitem(last=False)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)


def topic_key(topic: str) -> str:
    """Normalise a topic so trivial differences (case, spacing) hit the same entry."""
    return " ".join(topic.lower().split())
