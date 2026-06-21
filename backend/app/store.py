"""Durable primary store: query -> count, backed by SQLite.

The trie is fast but lives in memory and is lost on restart. This store is the
source of truth. Ingest loads the dataset here, then the trie is built from here.
"""

import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Iterator, Tuple

# One file next to the app package. Created on first run.
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "queries.db"


class Store:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI may read from different threads.
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS queries ("
            " query TEXT PRIMARY KEY,"
            " count INTEGER NOT NULL"
            ")"
        )
        self._conn.commit()

    def read_all(self) -> Iterator[Tuple[str, int]]:
        """Stream every (query, count). Used to rebuild the trie on startup."""
        cur = self._conn.execute("SELECT query, count FROM queries")
        yield from cur

    def upsert(self, query: str, delta: int = 1) -> int:
        """Increment count if the query exists, else insert it at `delta`.

        Returns the query's new total count, which the caller feeds to the trie
        so its top-k lists re-rank. The commit here is the synchronous, per-call
        disk write that Phase 6's batch writer will later replace.
        """
        self._conn.execute(
            "INSERT INTO queries (query, count) VALUES (?, ?) "
            "ON CONFLICT(query) DO UPDATE SET count = count + ?",
            (query, delta, delta),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT count FROM queries WHERE query = ?", (query,)
        ).fetchone()
        return row[0]

    def apply_deltas(self, deltas: Dict[str, int]) -> Dict[str, int]:
        """Apply many query -> delta increments in ONE transaction, then return
        the new totals for those queries so the caller can re-rank the trie.

        This is the batch writer's flush: one executemany and one commit for the
        whole batch, instead of one commit per submit. That single commit is the
        write-count win over Phase 3.
        """
        if not deltas:
            return {}
        items = list(deltas.items())
        self._conn.executemany(
            "INSERT INTO queries (query, count) VALUES (?, ?) "
            "ON CONFLICT(query) DO UPDATE SET count = count + excluded.count",
            items,
        )
        self._conn.commit()  # one commit for the entire batch
        keys = [q for q, _ in items]
        placeholders = ",".join("?" * len(keys))
        rows = self._conn.execute(
            f"SELECT query, count FROM queries WHERE query IN ({placeholders})", keys
        ).fetchall()
        return dict(rows)

    def bulk_load(self, rows: Iterable[Tuple[str, int]]) -> None:
        """Load many rows at once. executemany keeps it to one fast batch."""
        self._conn.executemany(
            "INSERT OR REPLACE INTO queries (query, count) VALUES (?, ?)",
            rows,
        )
        self._conn.commit()

    def get_count(self, query: str) -> int:
        """All-time count for one query, or 0 if unknown. Used by the trending
        blend to score a recently-hot query that isn't in a prefix's top-k yet.
        """
        row = self._conn.execute(
            "SELECT count FROM queries WHERE query = ?", (query,)
        ).fetchone()
        return row[0] if row else 0

    def count_rows(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]

    def close(self) -> None:
        self._conn.close()
