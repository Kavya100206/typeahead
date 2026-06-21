"""Recency-aware scoring via exponential time decay.

The professor's notes decay historical counts by 10% each day. That is
exponential decay; we do the continuous version: each query keeps a score that
shrinks as e^(-lambda * elapsed). A "half-life" sets lambda, so the score halves
every half_life_seconds of silence. A burst of searches lifts the score; once
the burst stops the score decays back down on its own. That single mechanism
fixes both failure modes: old queries fade, and one-off spikes do not stick.

This tracker holds only recency. The combined ranking (all-time popularity +
recency) is computed in main.py, which has access to the all-time counts.
"""

import math
import time
from typing import Dict, List, Tuple


class TrendingTracker:
    def __init__(self, half_life_seconds: float = 60.0) -> None:
        # lambda chosen so the score halves every half_life_seconds.
        self.decay_lambda = math.log(2) / half_life_seconds
        # query -> (score_at_last_update, last_update_time)
        self._scores: Dict[str, Tuple[float, float]] = {}

    def _now(self) -> float:
        return time.monotonic()

    def _decayed(self, score: float, last: float, now: float) -> float:
        return score * math.exp(-self.decay_lambda * (now - last))

    def record(self, query: str, weight: float = 1.0) -> None:
        """Register one search. Decay the existing score up to now, then add."""
        now = self._now()
        score, last = self._scores.get(query, (0.0, now))
        self._scores[query] = (self._decayed(score, last, now) + weight, now)

    def score(self, query: str) -> float:
        """Current decayed score for a query (0 if never seen)."""
        entry = self._scores.get(query)
        if entry is None:
            return 0.0
        score, last = entry
        return self._decayed(score, last, self._now())

    def top(self, k: int = 10) -> List[Tuple[str, float]]:
        """The k highest decayed scores right now, best first."""
        now = self._now()
        scored = [
            (q, self._decayed(s, last, now)) for q, (s, last) in self._scores.items()
        ]
        scored.sort(key=lambda qs: -qs[1])
        return scored[:k]

    def matching(self, prefix: str) -> List[str]:
        """Tracked queries that start with prefix. The set is small (only
        recently-searched queries), so a linear scan is fine.
        """
        return [q for q in self._scores if q.startswith(prefix)]

    def active_queries(self) -> List[str]:
        """All queries with any recent activity tracked. Used as trending
        candidates alongside the all-time popular set.
        """
        return list(self._scores.keys())
