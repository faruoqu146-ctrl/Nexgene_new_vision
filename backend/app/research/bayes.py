"""Bayes helpers (boot-safe)."""
from __future__ import annotations
import math
from typing import Optional

def shrink_effect(effect: float, se: float, prior_var: float = 0.25):
    if se <= 0:
        return effect, 0.0
    post_var = 1.0 / (1.0 / prior_var + 1.0 / (se * se))
    post_mean = post_var * (effect / (se * se))
    return post_mean, math.sqrt(post_var)

def log_bayes_factor_n0(effect: float, se: float, prior_sd: float = 0.5) -> Optional[float]:
    if se <= 0:
        return None
    v0 = se * se
    v1 = v0 + prior_sd * prior_sd
    return 0.5 * math.log(v0 / v1) + (effect * effect) * (1.0 / v0 - 1.0 / v1) / 2.0
