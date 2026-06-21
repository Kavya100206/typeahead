"""Evidence for the whole phase: adding a node remaps few keys on the ring,
but reshuffles almost everything under naive hash % N.

Run:  python scripts/remap_demo.py
"""

import hashlib
from pathlib import Path
import sys

# Allow running as a plain script: make `app` importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.cache.ring import HashRing, _hash


def make_keys(n: int = 5000) -> list:
    """A spread of prefix-like keys to route."""
    return [f"prefix{i}" for i in range(n)]


def consistent_hashing_remap(keys: list) -> float:
    ring = HashRing(virtual_nodes=100)
    for nid in ["node-0", "node-1", "node-2", "node-3"]:
        ring.add_node(nid)

    before = {k: ring.get_node(k) for k in keys}
    ring.add_node("node-4")  # scale out by one
    after = {k: ring.get_node(k) for k in keys}

    moved = sum(1 for k in keys if before[k] != after[k])
    return 100.0 * moved / len(keys)


def naive_modulo_remap(keys: list) -> float:
    def h(k: str) -> int:
        return int.from_bytes(hashlib.md5(k.encode()).digest()[:4], "big")

    before = {k: h(k) % 4 for k in keys}  # 4 nodes
    after = {k: h(k) % 5 for k in keys}   # add one -> 5 nodes
    moved = sum(1 for k in keys if before[k] != after[k])
    return 100.0 * moved / len(keys)


def main() -> None:
    keys = make_keys()
    ch = consistent_hashing_remap(keys)
    naive = naive_modulo_remap(keys)
    print(f"Adding a 5th node to 4, over {len(keys)} keys:")
    print(f"  consistent hashing : {ch:5.1f}% of keys remapped  (~1/5 = 20% expected)")
    print(f"  naive hash % N     : {naive:5.1f}% of keys remapped  (near-total miss storm)")


if __name__ == "__main__":
    main()
