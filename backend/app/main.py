"""FastAPI app and the read path.

Startup: open the store, build the trie from it, keep both in memory.
Request: GET /suggest?q=<prefix> -> normalize -> trie.top_k -> JSON.

The cache (Phase 4) will later sit between the route and the trie. The route
shape does not change.
"""

import math
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .batch_writer import BatchWriter
from .cache.cache_client import CacheClient
from .ingest import build_trie_from_store
from .store import Store
from .trending import TrendingTracker
from .util import normalize

# Holds the long-lived store and trie. Built once on startup, read per request.
state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = Store()
    state["store"] = store
    state["trie"] = build_trie_from_store(store)  # rebuild trie from durable data
    # Distributed cache: four logical nodes behind a consistent-hash ring.
    # /suggest still calls cache.get/set; the ring picks the node underneath.
    state["cache"] = CacheClient(
        node_ids=["node-0", "node-1", "node-2", "node-3"], ttl_seconds=30.0
    )
    # Batch writer: /search enqueues here instead of writing synchronously.
    batch = BatchWriter(store, state["trie"], batch_size=100, interval_seconds=5.0)
    batch.start()
    state["batch"] = batch
    # Trending: recency scores with a 60s half-life (short so a demo shows the
    # rise and fade in minutes, not days).
    state["trending"] = TrendingTracker(half_life_seconds=60.0)
    yield
    batch.stop()  # final flush so the last buffered submits are not lost
    store.close()


app = FastAPI(title="Search Typeahead", lifespan=lifespan)

# The frontend is served from a different origin (e.g. :5500) than this API
# (:8000). The browser's same-origin policy blocks that fetch unless the API
# opts in. Wide-open is fine for a local demo; a real deploy would list origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Trending score = log(1 + all_time_count) + WEIGHT * recent_activity.
#
# log(count) is a popularity baseline that compresses the huge count range
# (1,000,000 -> ~13.8, 1 -> ~0.7), so a genuine recent surge can compete with
# established queries. recent_activity is the decayed search score; one search
# adds ~1, which is negligible next to a popular query's baseline. So a query
# searched once cannot leapfrog iphone/amazon, but a sustained spike (many
# recent searches) accumulates and climbs, then fades as it decays.
RECENCY_WEIGHT = 1.0


def _trending_score(count: int, recency: float) -> float:
    return math.log1p(count) + RECENCY_WEIGHT * recency


def _enhanced_suggestions(prefix: str):
    """Recency-aware ranking for a prefix: merge the prefix's all-time top-k with
    any recently-active queries for that prefix, then rank by the trending score.

    We pull a wider candidate set (top 20) than we return so a query that is
    rising but not yet in the all-time top 10 still has a chance to surface.
    """
    trie = state["trie"]
    trending = state["trending"]
    store = state["store"]

    candidates = {query: count for query, count in trie.top_k(prefix, k=20)}
    for q in trending.matching(prefix):
        if q not in candidates:
            candidates[q] = store.get_count(q)
    if not candidates:
        return []

    scored = [
        (q, c, _trending_score(c, trending.score(q))) for q, c in candidates.items()
    ]
    scored.sort(key=lambda x: -x[2])
    return [
        {"query": q, "count": c, "score": round(s, 4)} for q, c, s in scored[:10]
    ]


@app.get("/suggest")
def suggest(q: str = Query(default=""), mode: str = Query(default="basic")):
    """Up to 10 completions for a prefix.

    mode=basic    : ranked by all-time count, served cache-aside (the fast path).
    mode=enhanced : recency-aware blend, recomputed every call (bypasses the
                    cache) because trending scores change too fast to cache.
    """
    prefix = normalize(q)
    if not prefix:
        # Empty or missing prefix: nothing to complete. Not an error.
        return {"prefix": prefix, "suggestions": []}

    if mode == "enhanced":
        # Trending changes constantly, so we recompute rather than cache (the
        # freshness-over-latency choice; effectively TTL=0 for this path).
        return {
            "prefix": prefix,
            "suggestions": _enhanced_suggestions(prefix),
            "source": "trending",
        }

    cache = state["cache"]
    cached = cache.get(prefix)
    if cached is not None:  # `is not None` so an empty-list hit still counts
        return {"prefix": prefix, "suggestions": cached, "source": "cache"}

    # Miss: compute from the source of truth (the trie), then fill the cache.
    results = state["trie"].top_k(prefix, k=10)
    suggestions = [{"query": query, "count": count} for query, count in results]
    cache.set(prefix, suggestions)
    return {"prefix": prefix, "suggestions": suggestions, "source": "trie"}


class SearchBody(BaseModel):
    query: str


@app.post("/search")
def search(body: SearchBody):
    """Record a submitted search. The submit goes into the batch writer's buffer
    and returns immediately; the store and trie are updated later on a flush.
    This is the Phase 6 replacement for Phase 3's synchronous per-submit write.
    """
    query = normalize(body.query)
    if not query:
        # Nothing to record, but the contract still returns the dummy message.
        return {"message": "Searched"}

    # Enqueue only: no disk write on the request path. The buffered count lands
    # in the store and trie on the next flush (size- or timer-triggered), so the
    # query may not appear in suggestions until then (eventual consistency).
    state["batch"].enqueue(query)
    # Trending is in-memory and updated per submit (not batched), so recency is
    # tracked in real time even though the durable count lags behind the flush.
    state["trending"].record(query)
    return {"message": "Searched"}


@app.get("/stats")
def stats():
    """Observability hook: the batch writer's submits vs actual DB writes (the
    Phase 6 reduction) and the cache's hit/miss numbers (Phase 8's hit rate).
    """
    return {"writes": state["batch"].stats(), "cache": state["cache"].stats()}


@app.get("/trending")
def trending(k: int = Query(default=10)):
    """Trending queries by `log(popularity) + weight * recency`, best first.

    Candidates are the all-time popular set (so the list is meaningful even with
    no recent activity) plus any recently active queries. With no recency the
    ranking is pure popularity; a sustained spike lifts a query above it and then
    fades. A query searched once stays near the bottom.
    """
    trie = state["trie"]
    tr = state["trending"]
    store = state["store"]

    # trie.top_k("") is the global top by all-time count (the root sees every
    # query). Union with recently active queries so a rising one can appear.
    candidates = {q: c for q, c in trie.top_k("", k=max(k * 3, 30))}
    for q in tr.active_queries():
        if q not in candidates:
            candidates[q] = store.get_count(q)

    scored = [(q, _trending_score(c, tr.score(q))) for q, c in candidates.items()]
    scored.sort(key=lambda x: -x[1])
    return {"trending": [{"query": q, "score": round(s, 4)} for q, s in scored[:k]]}


@app.get("/cache/debug")
def cache_debug(prefix: str = Query(default="")):
    """Which cache node owns this prefix, and whether that node currently holds
    it (hit) or not (miss). The window into the consistent-hash routing.
    """
    p = normalize(prefix)
    return state["cache"].debug(p)
