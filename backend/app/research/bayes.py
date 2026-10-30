"""Empirical-Bayes shrinkage and Bayes factors for the effect family.

With hundreds of simultaneous hypotheses the largest observed associations are, on
average, over-estimates (the winner's curse). A two-group empirical-Bayes model
estimates how many effects are truly zero and how large the non-zero ones tend to be,
then shrinks each estimate accordingly and reports the posterior probability that it
is non-null. Estimates live on the Fisher-z scale where the standard error is known.

Approximation note: the candidate tests share variables and are therefore dependent;
the mixture fit treats them as exchangeable, which is a standard approximation.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from .special import norm_cdf


def _npdf(x: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * (x / sd) ** 2) / (sd * math.sqrt(2.0 * math.pi))


def fit_two_group(z: Sequence[float], se: Sequence[float], iters: int = 300) -> dict:
    """Fit pi0 (null mass) and tau (slab sd) by EM on a tau grid (marginal likelihood)."""
    z, se = np.asarray(z, float), np.asarray(se, float)
    m = len(z)
    if m < 8:
        return {"pi0": 1.0, "tau": 0.0, "fitted": False, "n": m}
    f0 = _npdf(z, se)
    best = None
    for tau in np.concatenate(([0.02], np.linspace(0.05, 1.2, 24))):
        f1 = _npdf(z, np.sqrt(se ** 2 + tau ** 2))
        pi0 = 0.8
        for _ in range(iters):
            lfdr = pi0 * f0 / np.maximum(pi0 * f0 + (1 - pi0) * f1, 1e-300)
            new = float(np.clip(lfdr.mean(), 0.01, 0.999))
            if abs(new - pi0) < 1e-8:
                pi0 = new
                break
            pi0 = new
        ll = float(np.sum(np.log(np.maximum(pi0 * f0 + (1 - pi0) * f1, 1e-300))))
        if best is None or ll > best[0]:
            best = (ll, pi0, float(tau))
    return {"pi0": best[1], "tau": best[2], "fitted": True, "n": m, "loglik": best[0]}


def posterior(z: float, se: float, pi0: float, tau: float) -> dict:
    """Posterior summaries for one effect on the Fisher-z scale under the fitted two-group prior."""
    f0 = _npdf(np.array([z]), np.array([se]))[0]
    f1 = _npdf(np.array([z]), np.array([math.sqrt(se * se + tau * tau)]))[0]
    denom = max(pi0 * f0 + (1 - pi0) * f1, 1e-300)
    p_non_null = (1 - pi0) * f1 / denom
    shrink = (tau * tau) / (tau * tau + se * se) if tau > 0 else 0.0
    mu_slab = shrink * z
    sd_slab = math.sqrt(shrink) * se if tau > 0 else 0.0
    post_mean = p_non_null * mu_slab
    # variance of the mixture (null mass at zero)
    post_var = p_non_null * (sd_slab ** 2 + mu_slab ** 2) - post_mean ** 2
    return {"p_non_null": p_non_null, "lfdr": 1.0 - p_non_null, "z_shrunk": post_mean,
            "z_post_sd": math.sqrt(max(post_var, 0.0)), "slab_mean": mu_slab, "slab_sd": sd_slab}


def default_prior_summary(z: float, se: float, tau_alt: float, rope_z: float) -> dict:
    """Bayes factor / probability of direction / practical significance under a fixed N(0, tau_alt^2) prior."""
    v0 = se * se
    v1 = se * se + tau_alt * tau_alt
    log_bf10 = 0.5 * (math.log(v0) - math.log(v1)) + 0.5 * z * z * (1.0 / v0 - 1.0 / v1)
    shrink = tau_alt * tau_alt / v1
    mu, sd = shrink * z, math.sqrt(shrink) * se
    p_dir = norm_cdf(abs(mu) / sd) if sd > 0 else 0.5
    p_prac = 1.0 - (norm_cdf((rope_z - mu) / sd) - norm_cdf((-rope_z - mu) / sd)) if sd > 0 else float(abs(mu) > rope_z)
    return {"log10_bf10": log_bf10 / math.log(10.0), "p_direction": p_dir, "p_practical": p_prac,
            "posterior_mean_z": mu, "posterior_sd_z": sd}


def bf_label(log10_bf10: float) -> str:
    """Jeffreys-style verbal scale (descriptive only)."""
    a = abs(log10_bf10)
    side = "for an effect" if log10_bf10 > 0 else "for no effect"
    if a < 0.5 * math.log10(3):
        return "anecdotal"
    if a < 1.0:
        return f"moderate {side}"
    if a < 1.5:
        return f"strong {side}"
    if a < 2.0:
        return f"very strong {side}"
    return f"decisive {side}"
