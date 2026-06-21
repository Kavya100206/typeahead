"""Consistent-hashing ring: maps a key (prefix) to the node that owns it.

The ring is the hash space [0, 2^32) bent into a circle. Each physical node is
placed at many positions on it (virtual nodes) so load spreads evenly. To find
a key's owner, hash the key to a position and walk clockwise to the first node.

Why this over `hash(key) % N`: when N changes, modulo reshuffles almost every
key (a cache miss storm). On the ring, adding or removing a node only moves the
keys in that node's arc, about K/N of them.
"""

import bisect
import hashlib
from typing import Dict, List, Optional

# Size of the ring. We hash into [0, 2^32) so positions are plain 32-bit ints.
RING_SIZE = 2**32


def _hash(text: str) -> int:
    """Stable hash -> int in [0, 2^32).

    We use md5 (not Python's built-in hash()) because hash() is randomly salted
    per process, so node and key positions would differ on every restart. The
    ring needs the same key to land in the same place every run.
    """
    digest = hashlib.md5(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")  # first 4 bytes -> 32-bit int


class HashRing:
    def __init__(self, virtual_nodes: int = 100) -> None:
        self.virtual_nodes = virtual_nodes
        # Two parallel structures kept in sync and sorted by position:
        #   _positions[i] is a ring position, _owners[i] is the node id there.
        # Sorted so get_node can binary-search for the first position >= a key.
        self._positions: List[int] = []
        self._owners: List[str] = []

    def add_node(self, node_id: str) -> None:
        """Drop this node's virtual_nodes replicas onto the ring."""
        for replica in range(self.virtual_nodes):
            pos = _hash(f"{node_id}#{replica}")
            i = bisect.bisect_left(self._positions, pos)
            # Skip the rare exact collision; one missing replica out of 100
            # does not change the balance.
            if i < len(self._positions) and self._positions[i] == pos:
                continue
            self._positions.insert(i, pos)
            self._owners.insert(i, node_id)

    def remove_node(self, node_id: str) -> None:
        """Pull every replica of this node off the ring."""
        kept_positions: List[int] = []
        kept_owners: List[str] = []
        for pos, owner in zip(self._positions, self._owners):
            if owner != node_id:
                kept_positions.append(pos)
                kept_owners.append(owner)
        self._positions = kept_positions
        self._owners = kept_owners

    def get_node(self, key: str) -> Optional[str]:
        """Return the node id that owns this key, or None if the ring is empty.

        Hash the key, binary-search for the first ring position >= it, and wrap
        to index 0 when the key sits past the last position (the clockwise walk
        going over the top of the circle).
        """
        if not self._positions:
            return None
        pos = _hash(key)
        i = bisect.bisect_right(self._positions, pos)
        if i == len(self._positions):
            i = 0  # past the last node -> wrap around the ring
        return self._owners[i]
