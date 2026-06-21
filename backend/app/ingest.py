"""Bridge raw data into the two structures the app uses.

  load_csv_to_store:     data/queries.csv  ->  SQLite store (one time)
  build_trie_from_store: SQLite store       ->  in-memory trie (every startup)

The store persists; the trie is rebuilt from it whenever the server starts.
"""

import csv
from pathlib import Path

from .store import Store
from .trie import Trie
from .util import normalize

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "queries.csv"


def load_csv_to_store(store: Store, csv_path: Path = CSV_PATH) -> int:
    """Read the CSV, normalize queries, bulk load into the store. Returns rows loaded."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip the header row
        for row in reader:
            if len(row) < 2:
                continue
            query = normalize(row[0])
            if not query:
                continue
            try:
                count = int(row[1])
            except ValueError:
                continue  # skip malformed count
            rows.append((query, count))
    store.bulk_load(rows)
    return len(rows)


def build_trie_from_store(store: Store, k: int = 10) -> Trie:
    """Replay every (query, count) from the store into a fresh trie."""
    trie = Trie(k=k)
    for query, count in store.read_all():
        # is_new=True: the store has one row per query, so no duplicates to
        # dedup against. This is the fast path used only for the bulk build.
        trie.insert(query, count, is_new=True)
    return trie


def main() -> None:
    store = Store()
    n = load_csv_to_store(store)
    print(f"loaded {n} rows; store now holds {store.count_rows()} queries")
    store.close()


if __name__ == "__main__":
    main()
