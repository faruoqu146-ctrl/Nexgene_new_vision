"""Multiple-testing control for the hypothesis family."""
from __future__ import annotations

from typing import Sequence

import numpy as np


def bh_adjust(p: Sequence[float]) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q-values), monotone and capped at 1."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p, kind="mergesort")
    ranked = p[order] * m / (np.arange(m) + 1.0)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(m)
    q[order] = np.minimum(1.0, q_sorted)
    return q


def by_adjust(p: Sequence[float]) -> np.ndarray:
    """Benjamini-Yekutieli: FDR control under arbitrary dependence (conservative)."""
    m = len(p)
    if m == 0:
        return np.asarray(p, dtype=float)
    c = float(np.sum(1.0 / np.arange(1, m + 1)))
    return np.minimum(1.0, bh_adjust(p) * c)


def holm_adjust(p: Sequence[float]) -> np.ndarray:
    """Holm step-down adjusted p-values (family-wise error control)."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = np.argsort(p, kind="mergesort")
    adj = np.maximum.accumulate((m - np.arange(m)) * p[order])
    out = np.empty(m)
    out[order] = np.minimum(1.0, adj)
    return out


def storey_pi0(p: Sequence[float], lam: float = 0.5) -> float:
    """Storey's estimate of the proportion of true nulls (reported, never used for gating)."""
    p = np.asarray(p, dtype=float)
    if len(p) < 20:
        return 1.0
    return float(min(1.0, max(0.05, np.mean(p > lam) / (1.0 - lam))))
