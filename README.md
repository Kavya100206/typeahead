# Search Typeahead

A search typeahead system: as you type, it shows the top suggestions for your
prefix, ranked by all-time popularity or by a recency-aware score. Built to learn
and explain the HLD concepts behind it (trie + top-k, cache-aside + TTL,
consistent hashing, batch writes, recency scoring).

- Backend: Python + FastAPI, SQLite, in-process cache.
- Frontend: plain TypeScript (no framework, no bundler), compiled with `tsc`.

See [docs/architecture.md](docs/architecture.md) for the design and
[docs/performance-report.md](docs/performance-report.md) for measured numbers.

## Layout

```
backend/
  app/            FastAPI app, trie, store, cache, batch writer, trending
  scripts/        dataset generator + demos + benchmark
  data/           queries.csv (dataset) and queries.db (SQLite)
frontend/
  src/*.ts        debounce, api, ui, main
  index.html, style.css
docs/             architecture + performance report
```

## Prerequisites

- Python 3.10+
- Node 18+ (only to compile the TypeScript; the page itself runs framework-free)

## Backend

```bash
cd backend
pip install -r requirements.txt

# One time: generate the dataset (~120k rows) and load it into SQLite.
python scripts/generate_dataset.py
python -m app.ingest

# Run the API (rebuilds the trie from the store on startup, ~12s).
python -m uvicorn app.main:app --port 8000
```

API docs are auto-generated at http://localhost:8000/docs.

## Frontend

```bash
cd frontend
npm install
npm run build        # compiles src/*.ts -> dist/*.js  (use `npm run watch` while developing)
python -m http.server 5500
```

Open http://localhost:5500. Type to see suggestions; tick "Recency-aware ranking"
to switch to the enhanced ranking; the trending panel updates as searches come in.

## API

| Endpoint | Returns |
|----------|---------|
| `GET /suggest?q=<prefix>&mode=basic\|enhanced` | up to 10 suggestions; `basic` = all-time count (cached), `enhanced` = recency-aware blend |
| `POST /search` `{"query": "..."}` | `{"message": "Searched"}`; records the query via the batch writer |
| `GET /trending?k=10` | current trending queries by decayed recency score |
| `GET /cache/debug?prefix=<p>` | which cache node owns the prefix, and hit/miss |
| `GET /stats` | batch-writer submits vs DB writes, and cache hit/miss |

Edge cases handled by `/suggest`: empty input, missing `q`, mixed case
(normalized), and a prefix with no matches (empty list, not an error).

## Dataset

`scripts/generate_dataset.py` writes `data/queries.csv` (`query,count`, ~120k
rows) with prefix overlap and Zipf-like skew so the trie and ranking are actually
exercised. `python -m app.ingest` loads the CSV into SQLite; the trie is rebuilt
from SQLite on every server start.

## Demos and benchmark

```bash
cd backend
python scripts/remap_demo.py      # consistent hashing: ~17% remap vs ~80% for hash % N
python scripts/batch_demo.py      # batching: 1000 submits -> ~10 DB writes (100x)
python scripts/trending_demo.py   # a cold query rises on recency, then fades
python scripts/benchmark.py       # latency p95, cache hit rate, write reduction (server must be running)
```
