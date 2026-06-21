"""Show a cold query rising on recency, then fading once the burst stops.

Uses a short half-life so the whole rise-and-fade happens in a few seconds.
We compare the recency score of a spiking cold query against a steady popular
one to show that recency, not all-time count, drives trending.

Run:  python scripts/trending_demo.py
"""

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.trending import TrendingTracker


def main() -> None:
    # 2s half-life: scores halve every 2 seconds of silence.
    t = TrendingTracker(half_life_seconds=2.0)

    # A steady, mildly popular query: a few hits up front.
    for _ in range(5):
        t.record("steady query")

    # A cold query suddenly bursts (a trending event).
    print("burst: 50 hits for 'breaking news'")
    for _ in range(50):
        t.record("breaking news")

    print(f"\nright after burst:")
    for q, s in t.top(5):
        print(f"  {q:18s} score={s:7.2f}")

    # Stop searching it. Watch it decay over the next few seconds.
    for elapsed in (2, 4, 6):
        time.sleep(2)
        bn = t.score("breaking news")
        sq = t.score("steady query")
        print(f"\nafter {elapsed}s of silence:")
        print(f"  breaking news      score={bn:7.2f}")
        print(f"  steady query       score={sq:7.2f}")

    print("\n'breaking news' rose far above 'steady query', then decayed back down.")


if __name__ == "__main__":
    main()
