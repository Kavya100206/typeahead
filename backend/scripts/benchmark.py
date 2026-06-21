"""Measure the three numbers the rubric wants, against a running server.

  1. /suggest latency: mean and p95, on a cold (miss) pass vs a warm (hit) pass.
  2. Cache hit rate over a realistic, skewed prefix mix.
  3. Write reduction: submits vs actual DB writes through the batch writer.

Start the server first (python -m uvicorn app.main:app --port 8000), then:
  python scripts/benchmark.py
"""

import random
import string
import time

import httpx

BASE = "http://localhost:8000"
random.seed(7)


def percentile(values, pct):
    """Value at the given percentile (e.g. 0.95) of a list of numbers."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(pct * len(ordered)))
    return ordered[idx]


def two_letter_prefixes():
    return [a + b for a in string.ascii_lowercase for b in string.ascii_lowercase]


def measure_latency(client):
    prefixes = two_letter_prefixes()  # 676 distinct prefixes

    # Cold pass: first touch of each prefix is a cache miss (trie walk + fill).
    miss = []
    for p in prefixes:
        t0 = time.perf_counter()
        client.get(f"{BASE}/suggest", params={"q": p})
        miss.append((time.perf_counter() - t0) * 1000)

    # Warm pass: same prefixes again, now served from cache (hits).
    hit = []
    for p in prefixes:
        t0 = time.perf_counter()
        client.get(f"{BASE}/suggest", params={"q": p})
        hit.append((time.perf_counter() - t0) * 1000)

    print("== /suggest latency (ms) ==")
    print(f"  miss : mean={sum(miss)/len(miss):.2f}  p95={percentile(miss,0.95):.2f}")
    print(f"  hit  : mean={sum(hit)/len(hit):.2f}  p95={percentile(hit,0.95):.2f}")


def measure_hit_rate(client):
    before = client.get(f"{BASE}/stats").json()["cache"]

    # Realistic skew: a few popular prefixes dominate, plus a random tail.
    popular = ["ip", "ja", "py", "do", "aw", "re", "an", "ch"]
    stream = []
    for _ in range(2000):
        if random.random() < 0.8:
            stream.append(random.choice(popular))  # 80% to hot prefixes
        else:
            stream.append(random.choice(string.ascii_lowercase) + random.choice(string.ascii_lowercase))
    for p in stream:
        client.get(f"{BASE}/suggest", params={"q": p})

    after = client.get(f"{BASE}/stats").json()["cache"]
    d_hits = after["hits"] - before["hits"]
    d_miss = after["misses"] - before["misses"]
    total = d_hits + d_miss
    rate = d_hits / total if total else 0.0
    print("== cache hit rate (realistic mix, 2000 reads) ==")
    print(f"  hits={d_hits}  misses={d_miss}  hit_rate={rate:.1%}")


def measure_write_reduction(client):
    before = client.get(f"{BASE}/stats").json()["writes"]

    queries = ["iphone", "ipad", "java", "python", "docker", "aws"]
    submits = 600
    for _ in range(submits):
        client.post(f"{BASE}/search", json={"query": random.choice(queries)})

    time.sleep(6)  # let a timer flush catch any remainder
    after = client.get(f"{BASE}/stats").json()["writes"]
    d_submits = after["submits"] - before["submits"]
    d_writes = after["db_writes"] - before["db_writes"]
    print("== write reduction (batch writer) ==")
    print(f"  submits={d_submits}  db_writes={d_writes}  reduction={d_submits/max(1,d_writes):.0f}x")


def main():
    with httpx.Client(timeout=30) as client:
        measure_latency(client)
        measure_hit_rate(client)
        measure_write_reduction(client)


if __name__ == "__main__":
    main()
