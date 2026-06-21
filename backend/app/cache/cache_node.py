"""One logical cache node: an in-memory dict with per-entry TTL.

Key   = a normalized prefix (e.g. "ip").
Value = the top-k suggestion list we would return for that prefix.

This is the cache-aside store. The caller (the /suggest route) does the
check-miss-fill dance; this node only holds entries, expires them, and counts
hits and misses. Phase 5 runs several of these behind a consistent-hash ring.
"""

import time
from typing import Any, Dict, Optional, Tuple


class CacheNode:
    def __init__(self, ttl_seconds: float = 30.0, node_id: str = "node-0") -> None:
        self.ttl = ttl_seconds
        self.node_id = node_id  # used by Phase 5's /cache/debug
        # key -> (value, expiry). Expiry is a monotonic timestamp, so it is
        # immune to system clock changes (NTP jumps, DST) that wall-clock isn't.
        self._data: Dict[str, Tuple[Any, float]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Return the cached value, or None on a miss. A present-but-expired
        entry is a miss: we drop it (lazy expiry) and report the miss.
        """
        entry = self._data.get(key)
        if entry is None:
            self.misses += 1
            return None

        value, expiry = entry
        if time.monotonic() >= expiry:
            del self._data[key]  # expired: evict now, count as a miss
            self.misses += 1
            return None

        self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value with a fresh expiry of now + ttl."""
        self._data[key] = (value, time.monotonic() + self.ttl)

    def contains(self, key: str) -> bool:
        """Peek whether a live (non-expired) entry exists. Does not count as a
        hit or miss. Used by /cache/debug to report state without disturbing it.
        """
        entry = self._data.get(key)
        return entry is not None and time.monotonic() < entry[1]

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return self.hits / total if total else 0.0

    def stats(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hit_rate, 3),
            "size": len(self._data),
            "ttl_seconds": self.ttl,
        }
