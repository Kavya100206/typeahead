"""Prefix tree with a precomputed top-k list at every node.

Reads are the common case, so we make them O(p) to walk the prefix plus O(1) to
read the node's cached list. We pay for that on insert: every node on a query's
path refreshes its top-k. More memory and more work on write, fast reads. That
trade is correct here because reads vastly outnumber writes.
"""

import bisect
from typing import Dict, List, Tuple


class TrieNode:
    # __slots__ avoids a per-node __dict__, saving memory across many nodes.
    __slots__ = ("children", "top_k")

    def __init__(self) -> None:
        self.children: Dict[str, "TrieNode"] = {}
        # Sorted best-first: list of (-count, query). At most k entries.
        # We store the count negated so plain tuple order is already
        # "highest count first, ties alphabetical" -- no sort key callback.
        self.top_k: List[Tuple[int, str]] = []


class Trie:
    def __init__(self, k: int = 10) -> None:
        self.root = TrieNode()
        self.k = k

    def insert(self, query: str, count: int, is_new: bool = False) -> None:
        """Add or update a query, refreshing top-k on every node of its path.

        Set is_new=True only during the one-time bulk build from the dataset,
        where every query is unique. It skips the dedup scan that live updates
        (Phase 3 increments) need, which roughly halves the build time.
        """
        node = self.root
        self._update_top_k(node, query, count, is_new)  # root sees all queries
        for ch in query:
            node = node.children.setdefault(ch, TrieNode())
            self._update_top_k(node, query, count, is_new)

    def _update_top_k(
        self, node: TrieNode, query: str, count: int, is_new: bool = False
    ) -> None:
        tk = node.top_k
        # On a live update the same query may already be in the list with an old
        # count, so drop the stale copy first. The list is tiny (<= k), so this
        # linear scan is cheap. The bulk build skips it: the dataset has no repeats.
        if not is_new:
            for i, (_, q) in enumerate(tk):
                if q == query:
                    del tk[i]
                    break
        entry = (-count, query)
        # Skip the work entirely when the list is full and this entry cannot
        # beat the current worst (tk[-1]). Near the root the list is full of
        # huge counts, so almost every candidate is rejected by this one
        # comparison -- that is what makes the bulk build fast.
        if len(tk) < self.k or entry < tk[-1]:
            bisect.insort(tk, entry)  # keep best-first order, no full re-sort
            if len(tk) > self.k:
                tk.pop()  # the worst entry is now last; drop it

    def top_k(self, prefix: str, k: int = 10) -> List[Tuple[str, int]]:
        """Walk to the prefix node and return its cached list as (query, count)."""
        node = self.root
        for ch in prefix:
            node = node.children.get(ch)
            if node is None:
                return []  # no query starts with this prefix
        # Stored negated and best-first; flip the sign back for the caller.
        return [(q, -neg) for (neg, q) in node.top_k[:k]]
