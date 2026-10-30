"""Multiple-testing corrections (boot-safe)."""
from __future__ import annotations
from typing import List, Sequence

def holm(p_values: Sequence[float]) -> List[float]:
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adj = [0.0] * n
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, p_values[i] * (n - rank)))
        adj[i] = running
    return adj

def benjamini_hochberg(p_values: Sequence[float], q: float = 0.10) -> List[bool]:
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    reject = [False] * n
    max_k = -1
    for rank, i in enumerate(order, start=1):
        if p_values[i] <= (rank / n) * q:
            max_k = rank
    for rank, i in enumerate(order, start=1):
        reject[i] = rank <= max_k
    return reject
