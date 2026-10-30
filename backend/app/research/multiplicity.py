"""Multiple-testing corrections used by the discovery pipeline."""
from __future__ import annotations

from typing import Iterable, List, Sequence


def holm(p_values: Sequence[float]) -> List[float]:
    """Holm–Bonferroni adjusted p-values (same order as input)."""
    n = len(p_values)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: p_values[i])
    adj = [0.0] * n
    running = 0.0
    for rank, i in enumerate(order):
        factor = n - rank
        val = min(1.0, p_values[i] * factor)
        running = max(running, val)
        adj[i] = running
    return adj


def benjamini_hochberg(p_values: Sequence[float], q: float = 0.10) -> List[bool]:
    """BH rejection decisions at FDR level q."""
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
        if rank <= max_k:
            reject[i] = True
    return reject
