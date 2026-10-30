"""Meta-analysis helpers (fixed/random effects) for repeated personal trials."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


@dataclass
class MetaResult:
    effect: float
    se: float
    n_studies: int
    method: str


def fixed_effect(effects: Sequence[float], ses: Sequence[float]) -> MetaResult:
    """Inverse-variance fixed-effect estimate."""
    if not effects:
        return MetaResult(0.0, float("inf"), 0, "fixed")
    w = [1.0 / (s * s) if s > 0 else 0.0 for s in ses]
    sw = sum(w) or 1.0
    mu = sum(wi * ei for wi, ei in zip(w, effects)) / sw
    se = math.sqrt(1.0 / sw)
    return MetaResult(mu, se, len(effects), "fixed")
