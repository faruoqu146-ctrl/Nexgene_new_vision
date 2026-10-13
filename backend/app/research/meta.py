"""Random-effects meta-analysis for pooling per-person effect estimates (privacy-gated).

Population pooling is the long-term route to informative priors across many people. This
module is only the mathematics: it refuses to pool fewer than ``MIN_PEOPLE`` estimates so a
pooled result can never be traced back to one person. Collecting estimates across users needs
consent and governance that are NOT implemented here.
"""
from __future__ import annotations

import math
from typing import Sequence

from .special import t_ppf, t_two_sided_p

MIN_PEOPLE = 10


def random_effects(estimates: Sequence[float], ses: Sequence[float], min_people: int = MIN_PEOPLE) -> dict:
    """DerSimonian-Laird random effects with Hartung-Knapp interval, I^2 and a prediction interval."""
    k = len(estimates)
    if k != len(ses):
        raise ValueError("estimates and ses must have equal length")
    if k < min_people:
        return {"pooled": False, "reason": f"need at least {min_people} people to pool (have {k})"}
    if any(s <= 0 for s in ses):
        raise ValueError("standard errors must be positive")
    w = [1.0 / (s * s) for s in ses]
    sw = sum(w)
    fixed = sum(wi * yi for wi, yi in zip(w, estimates)) / sw
    q = sum(wi * (yi - fixed) ** 2 for wi, yi in zip(w, estimates))
    c = sw - sum(wi * wi for wi in w) / sw
    tau2 = max(0.0, (q - (k - 1)) / c) if c > 0 else 0.0
    ws = [1.0 / (s * s + tau2) for s in ses]
    sws = sum(ws)
    mu = sum(wi * yi for wi, yi in zip(ws, estimates)) / sws
    hk = sum(wi * (yi - mu) ** 2 for wi, yi in zip(ws, estimates)) / ((k - 1) * sws)
    se = math.sqrt(max(hk, 1.0 / sws))                     # Hartung-Knapp, floored at the classical variance
    crit = t_ppf(0.975, k - 1)
    i2 = max(0.0, (q - (k - 1)) / q) if q > 0 else 0.0
    pred_se = math.sqrt(tau2 + se * se)
    crit_p = t_ppf(0.975, max(1, k - 2))
    return {
        "pooled": True, "k": k, "mean": mu, "se": se, "ci95": [mu - crit * se, mu + crit * se],
        "p": t_two_sided_p(abs(mu / se), k - 1), "tau2": tau2, "tau": math.sqrt(tau2), "i2": i2, "q": q,
        "prediction_interval95": [mu - crit_p * pred_se, mu + crit_p * pred_se],
    }


def population_prior(estimates: Sequence[float], ses: Sequence[float]) -> dict:
    """Empirical-Bayes prior N(mu, tau^2) for a new person's effect, from pooled estimates."""
    res = random_effects(estimates, ses)
    if not res["pooled"]:
        return {"available": False, "reason": res["reason"]}
    return {"available": True, "mean": res["mean"], "sd": max(res["tau"], 0.05), "k": res["k"]}
