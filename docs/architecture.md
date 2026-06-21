# Architecture

Search typeahead: as a user types, the UI shows the top suggestions for the
typed prefix, ranked by popularity (and optionally recency). Submitting a search
records the query so popularity stays current.

The one fact that drives every decision: **reads vastly outnumber writes.** Every
keystroke is a read; only a submit is a write. So we optimize the read path hard
and are allowed to make writes slower or delayed.

## Diagram

```
  browser ── debounce ──> GET /suggest?q=<prefix>&mode=basic|enhanced
     ▲                          │
     │ top 10                   ▼
     │                   ┌──────────────┐   hit
     │                   │ CacheClient  │────────> return cached top-10
     │                   │  + hash ring │
     │                   └──────┬───────┘   miss
     │                          ▼
     │                       Trie.top_k(prefix)  ── fills cache ──> return
     │
  Enter / click ──> POST /search ──> BatchWriter.enqueue(query)
                                       (aggregate query -> delta)
                                       flush on size OR timer
                                          │
                                          ▼
                                   SQLite store (query -> count)
                                   + Trie re-rank
     GET /trending ──> TrendingTracker.top()      (decayed recency scores)
```

## Components

| Component | File | Job |
|-----------|------|-----|
| Trie | `app/trie.py` | prefix match + precomputed top-k at every node |
| Primary store | `app/store.py` | durable `query -> count`, source of truth, rebuilds the trie on startup |
| Cache node | `app/cache/cache_node.py` | one logical cache with TTL + hit/miss counters |
| Hash ring | `app/cache/ring.py` | consistent hashing, prefix -> node |
| Cache client | `app/cache/cache_client.py` | front door for reads; routes to the owning node |
| Batch writer | `app/batch_writer.py` | buffer + aggregate + flush writes |
| Trending | `app/trending.py` | recency-aware scoring via time decay |
| Ingest | `app/ingest.py` | load dataset into store, build trie |
| API | `app/main.py` | the routes |
| Frontend | `frontend/src/*.ts` | UI, debounce, keyboard nav, trending panel |

## Read path

1. `GET /suggest?q=ip` -> normalize the prefix.
2. `CacheClient` hashes the prefix on the ring to pick the owning `CacheNode`.
3. Hit: return the cached top-10. Miss: `Trie.top_k` walks the prefix node and
   reads its precomputed list, fill the cache, return.
4. `mode=enhanced` skips the cache and blends all-time count with the decayed
   recency score, so a freshly hot query can outrank an old one.

## Write path

1. `POST /search` -> `BatchWriter.enqueue(query)` and return immediately.
2. Submits aggregate in a `query -> delta` map. The buffer flushes on a size
   threshold or a timer, whichever first.
3. A flush applies all deltas to SQLite in one transaction and re-ranks the trie.
4. `TrendingTracker.record` runs per submit (in memory) so recency is live even
   though the durable count lags until the flush.

## Design rationale (why these, not the alternatives)

- **Trie with precomputed top-k vs computing top-k per query.** Storing the top-k
  at each node makes a read O(p) to walk the prefix plus O(1) to read the list, at
  the cost of more work on insert. Correct here because reads dominate.

- **Trie vs a flat prefix -> top-k key-value store (the HLD "Approach 2").** These
  are the same data: a trie node *is* a prefix, and its augmented top-k *is* the
  cached value for that prefix. A trie is just the shared-prefix-compressed,
  single-machine form of that key-value store. At many-server scale you flatten it
  to a hashmap and shard by `hash(prefix)` (tries shard badly; no DB is built for
  them) which is exactly what our cache layer + consistent-hash ring do. So we
  implement Approach 2's distributed prefix cache, with the trie as its in-memory
  source. The read path uses cache-aside + TTL rather than a write-through
  authoritative cache; both are standard, this one keeps the app in control.

- **Cache-aside + TTL vs explicit invalidation.** TTL is simple: every entry
  expires and is re-fetched. Pinpoint invalidation is harder (which prefixes does
  one query update touch?), so TTL is the default; trending sidesteps staleness by
  recomputing instead of caching.

- **Consistent hashing vs `hash % N`.** Modulo reshuffles almost every key when N
  changes (a cache miss storm). The ring moves only ~K/N keys. Virtual nodes keep
  the load even. Measured: adding a 5th node to 4 remaps ~17% of keys vs ~80% with
  modulo.

- **Batch writes vs synchronous writes.** Synchronous writes tie request latency
  to disk and hammer hot rows. The aggregating buffer turns many submits into one
  bulk commit per flush (measured ~100x fewer writes). This is the LSM memtable
  idea; the durability gap (a crash loses the buffer) is why real LSM systems keep
  a write-ahead log. We mitigate with a flush on shutdown.

- **Time decay vs sliding window for trending.** Decay keeps one score per query
  and shrinks it over time (`score = score * e^(-lambda*dt) + 1`). Cheap and
  smooth; a window is exact but needs bucket bookkeeping. Decay fixes both failure
  modes: old queries fade, and a one-off spike fades once the burst stops.

## Consistency (CAP touchpoint)

The cache and the store can disagree for up to a TTL window, and batched writes
land later than the submit. So the read path is **eventually consistent**, traded
for low latency and far fewer writes. On a single box this is a deliberate choice,
not a partition-tolerance claim; it is the standard latency-vs-freshness trade.
