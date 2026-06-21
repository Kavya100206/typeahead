"""Aggregating write buffer: turn many search submits into few DB writes.

Instead of writing to the store on every submit (Phase 3), we buffer submits in
a map of query -> delta. Duplicates collapse: 50 submits of "iphone" become one
entry {"iphone": 50}. The buffer flushes to the store in a single transaction
when it reaches a size threshold OR when a background timer fires, whichever
comes first.

This is the same move as an LSM tree's memtable: batch writes in memory, flush
in bulk. The cost is durability: a crash before a flush loses the buffered
counts. We mitigate by flushing on shutdown; a real system would add a
write-ahead log.
"""

import threading
from typing import Dict


class BatchWriter:
    def __init__(
        self,
        store,
        trie,
        batch_size: int = 100,
        interval_seconds: float = 5.0,
    ) -> None:
        self.store = store
        self.trie = trie
        self.batch_size = batch_size
        self.interval = interval_seconds

        # The aggregating buffer and the lock that guards it. enqueue() (request
        # threads) and flush() (timer thread) both touch it, so every access is
        # under the lock.
        self._buffer: Dict[str, int] = {}
        self._pending = 0  # submits buffered since the last flush (for size trigger)
        self._lock = threading.Lock()

        # Counters for the before/after story vs Phase 3.
        self.submits = 0     # total enqueued, ever
        self.db_writes = 0   # total flushes that hit the DB (one commit each)

        self._timer: threading.Timer | None = None
        self._stopped = False

    # --- Lifecycle ------------------------------------------------------------

    def start(self) -> None:
        """Begin the periodic timer flush."""
        self._schedule()

    def stop(self) -> None:
        """Stop the timer and flush whatever is buffered, so shutdown does not
        silently drop the last batch.
        """
        self._stopped = True
        if self._timer is not None:
            self._timer.cancel()
        self.flush()

    def _schedule(self) -> None:
        if self._stopped:
            return
        self._timer = threading.Timer(self.interval, self._on_timer)
        self._timer.daemon = True  # do not block process exit
        self._timer.start()

    def _on_timer(self) -> None:
        self.flush()
        self._schedule()  # re-arm for the next interval

    # --- Write path -----------------------------------------------------------

    def enqueue(self, query: str) -> None:
        """Record a submit. Aggregates into the buffer; may trigger a size flush."""
        with self._lock:
            self._buffer[query] = self._buffer.get(query, 0) + 1
            self._pending += 1
            self.submits += 1
            full = self._pending >= self.batch_size
        # Flush outside the lock so we are not holding it during DB / trie work.
        if full:
            self.flush()

    def flush(self) -> None:
        """Apply the buffered deltas to the store and trie in one batch.

        We swap the buffer out under the lock (grab it, leave an empty one),
        then do the slow DB and trie work without the lock held. Whichever
        caller wins the swap owns this batch; a concurrent flush sees an empty
        buffer and returns.
        """
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = {}
            self._pending = 0

        new_counts = self.store.apply_deltas(batch)  # one transaction, one commit
        for query, count in new_counts.items():
            self.trie.insert(query, count)  # re-rank top-k with the new total
        self.db_writes += 1

    # --- Introspection --------------------------------------------------------

    def stats(self) -> Dict[str, int]:
        with self._lock:
            buffered = self._pending
        return {
            "submits": self.submits,
            "db_writes": self.db_writes,
            "buffered": buffered,
        }
