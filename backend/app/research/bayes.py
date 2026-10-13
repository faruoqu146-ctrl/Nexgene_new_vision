"""Empirical-Bayes shrinkage and Bayes factors for the effect family.

With hundreds of simultaneous tests, classical p-values alone are not enough.
This module provides:
- Empirical-Bayes shrinkage of effect sizes toward a prior
- Bayes factors for competing hypotheses
- Posterior probability of a true effect
"""

from __future__ import annotations

import numpy as np
from typing import Optional, Tuple

from .config import ResearchConfig


def empirical_bayes_shrink(
    effects: np.ndarray,
    se: np.ndarray,
    prior_var: Optional[float] = None,
) -> Tuple[np.ndarray, float]:
    """Shrink effect estimates toward zero using empirical Bayes.

    Returns shrunk effects and estimated prior variance.
    """
    effects = np.asarray(effects, dtype=float)
    se = np.asarray(se, dtype=float)
    var = se ** 2
    if prior_var is None:
        # Method of moments for prior variance
        excess = effects**2 - var
        prior_var = max(0.0, float(np.mean(excess[excess > 0])) if np.any(excess > 0) else 0.0)
    shrink = var / (var + prior_var + 1e-12)
    shrunk = effects * (1 - shrink)
    return shrunk, prior_var
