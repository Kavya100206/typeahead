"""Proof of the write-count drop: 1000 submits, far fewer DB writes.

Drives the BatchWriter directly against a throwaway store, so it does not touch
the real queries.db. Compares the naive Phase 3 cost (one commit per submit)
with the Phase 6 batched cost (one commit per flush).

Run:  python scripts/batch_demo.py
"""

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.batch_writer import BatchWriter
from app.store import Store
from app.trie import Trie


def main() -> None:
    tmp = Path(tempfile.gettempdir()) / "batch_demo.db"
    if tmp.exists():
        tmp.unlink()
    store = Store(db_path=tmp)
    trie = Trie()

    # 1000 submits, only 3 distinct queries: the hot-query skew batching loves.
    submits = ["iphone"] * 500 + ["ipad"] * 300 + ["java"] * 200

    # Large interval so the timer never fires here; size triggers do the work,
    # plus the final flush on stop(). Keeps the demo deterministic.
    bw = BatchWriter(store, trie, batch_size=100, interval_seconds=9999)
    bw.start()
    for q in submits:
        bw.enqueue(q)
    bw.stop()  # final flush of whatever remains

    naive = len(submits)  # Phase 3 would commit once per submit
    print(f"submits            : {bw.submits}")
    print(f"naive DB writes    : {naive}   (Phase 3: one commit per submit)")
    print(f"batched DB writes  : {bw.db_writes}    (Phase 6: one commit per flush)")
    print(f"reduction          : {naive / bw.db_writes:.0f}x fewer writes")
    print(
        "final counts       : "
        f"iphone={trie.top_k('iphone')[0][1]}, "
        f"ipad={trie.top_k('ipad')[0][1]}, "
        f"java={trie.top_k('java')[0][1]}  (aggregation preserved every count)"
    )

    store.close()
    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
