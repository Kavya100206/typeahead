"""Front door for the distributed cache.

Holds N CacheNode objects and a HashRing. Every get/set asks the ring which
node owns the prefix, then delegates to that node. The /suggest route talks to
this client and never sees the ring or the individual nodes, so the cache-aside
flow from Phase 4 is unchanged; only the storage location of each prefix moves.
"""

from typing import Any, Dict, List, Optional

from .cache_node import CacheNode
from .ring import HashRing


class CacheClient:
    def __init__(
        self,
        node_ids: List[str],
        ttl_seconds: float = 30.0,
        virtual_nodes: int = 100,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.ring = HashRing(virtual_nodes=virtual_nodes)
        self.nodes: Dict[str, CacheNode] = {}
        for node_id in node_ids:
            self._spin_up(node_id)

    def _spin_up(self, node_id: str) -> None:
        self.nodes[node_id] = CacheNode(ttl_seconds=self.ttl_seconds, node_id=node_id)
        self.ring.add_node(node_id)

    def _node_for(self, prefix: str) -> CacheNode:
        """The CacheNode the ring assigns this prefix to."""
        node_id = self.ring.get_node(prefix)
        return self.nodes[node_id]

    # --- The read-path interface /suggest uses (same shape as CacheNode) ------

    def get(self, prefix: str) -> Optional[Any]:
        return self._node_for(prefix).get(prefix)

    def set(self, prefix: str, value: Any) -> None:
        self._node_for(prefix).set(prefix, value)

    # --- Scaling and introspection -------------------------------------------

    def add_node(self, node_id: str) -> None:
        """Add a node at runtime. Thanks to the ring, only the prefixes in this
        node's arc change owners; everything else keeps its existing node.
        """
        self._spin_up(node_id)

    def owner_of(self, prefix: str) -> Optional[str]:
        """Which node id owns this prefix, without touching the cache."""
        return self.ring.get_node(prefix)

    def debug(self, prefix: str) -> Dict[str, Any]:
        """For /cache/debug: the owning node and whether it currently holds the
        prefix. Uses contains(), so it does not register a hit or miss.
        """
        node_id = self.ring.get_node(prefix)
        present = self.nodes[node_id].contains(prefix)
        return {
            "prefix": prefix,
            "node_id": node_id,
            "cached": present,
            "status": "hit" if present else "miss",
        }

    def stats(self) -> Dict[str, Any]:
        hits = sum(n.hits for n in self.nodes.values())
        misses = sum(n.misses for n in self.nodes.values())
        total = hits + misses
        return {
            "num_nodes": len(self.nodes),
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hits / total, 3) if total else 0.0,
            "nodes": [n.stats() for n in self.nodes.values()],
        }
