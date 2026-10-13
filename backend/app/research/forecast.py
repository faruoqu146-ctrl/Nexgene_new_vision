"""Locked-model forward testing (temporal validation with sequential evidence).

Protocol
  1. FREEZE: when a hypothesis reaches ERL-2, its effect (shrunk toward zero to undo
     the winner's curse), noise level and weekday pattern are frozen and hashed. The
     model never sees later data.
  2. SCORE: for every later day with both the exposure and the outcome observed, the
     frozen model is compared with a *no-effect* model that has the same weekday and
     local-level terms. The comparison is a log-likelihood ratio on the unseen day.
  3. ACCUMULATE: log-ratios add up across days and across successive freezes. Because
     each prediction is made before its outcome is known, the running product is a
     valid sequential test statistic: under "no effect" the chance it ever reaches
     1/alpha is at most alpha (Ville's inequality; approximate here because the noise
     level is estimated). 20 is the conventional alpha = 0.05 threshold.

Local-level formulation: the outcome baseline is the person's trailing 14-day mean and
the exposure reference its trailing 28-day mean, so slow drift is absorbed by both
models and cannot masquerade as an effect.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional

import numpy as np

from .config import DEFAULT_CONFIG, EngineConfig
from .panel import Panel
from .provenance import canonical_json, sha256_hex
from .special import beta_cdf

Y_WINDOW = 14
X_WINDOW = 28
Y_MIN_OBS = 5
X_MIN_OBS = 7


def _trailing_mean(arr: np.ndarray, end_exclusive: int, window: int, min_obs: int) -> Optional[float]:
    lo = max(0, end_exclusive - window)
    seg = arr[lo:end_exclusive]
    seg = seg[~np.isnan(seg)]
    return float(seg.mean()) if len(seg) >= min_obs else None


def _weekday_offsets(y: np.ndarray, weekdays: np.ndarray, upto: int) -> list:
    """Shrunken weekday offsets of the outcome from the training window."""
    seg, wd = y[:upto], weekdays[:upto]
    m = ~np.isnan(seg)
    if m.sum() < 14:
        return [0.0] * 7
    overall = float(seg[m].mean())
    out = []
    for k in range(7):
        sel = m & (wd == k)
        n = int(sel.sum())
        out.append(float((seg[sel].mean() - overall) * n / (n + 2.0)) if n else 0.0)
    return out


def freeze_model(panel: Panel, cand: dict, cfg: EngineConfig = DEFAULT_CONFIG) -> Optional[dict]:
    """Freeze a candidate's effect model using only data in ``panel``. Returns a JSON-able dict."""
    x, y = panel.variables.get(cand["exposure"]), panel.variables.get(cand["outcome"])
    if x is None or y is None:
        return None
    lag = int(cand["lag"])
    T = panel.T
    r_adj = cand["effect"]["r_adj"]
    r_shr = cand["bayes"]["r_shrunk"]
    if not r_adj or math.isnan(r_adj):
        return None
    shrink = float(min(1.0, max(0.0, r_shr / r_adj))) if r_adj else 0.0
    beta = float(cand["effect"]["beta"]) * shrink
    sd_x = float(cand["effect"]["exposure_sd"] or 0.0)
    if sd_x <= 0 or not math.isfinite(beta):
        return None
    wd_off = _weekday_offsets(y, panel.weekdays, T)
    # training-time predictive sd of the baseline forecast (one-step, past data only)
    errs = []
    for t in range(Y_WINDOW, T):
        if np.isnan(y[t]):
            continue
        base = _trailing_mean(y, t, Y_WINDOW, Y_MIN_OBS)
        if base is None:
            continue
        errs.append(y[t] - base - wd_off[int(panel.weekdays[t])])
    if len(errs) < 10:
        return None
    sigma = float(np.std(errs, ddof=1))
    if sigma <= 0:
        return None
    return {
        "candidate_id": cand["id"], "exposure": cand["exposure"], "outcome": cand["outcome"], "lag": lag,
        "frozen_through": panel.dates[-1].isoformat(), "beta": beta, "beta_unshrunk": float(cand["effect"]["beta"]),
        "shrink_factor": shrink, "sigma": sigma, "sd_x": sd_x, "weekday_offsets": wd_off, "n_training_errors": len(errs),
        "y_window_days": Y_WINDOW, "x_window_days": X_WINDOW, "informative_sd_multiple": cfg.forecast_informative_sd,
        "sign": 1 if beta > 0 else -1,
    }


def preregistration(model: dict, issued_at: str, horizon_days: int) -> dict:
    body = {
        "protocol": "locked-model-forward-test-v1", "model": model, "horizon_days": int(horizon_days),
        "comparison": "log-likelihood ratio of frozen-effect model vs no-effect model (same weekday + local-level terms)",
        "evidence_ratio_confirm": DEFAULT_CONFIG.evidence_ratio_confirm,
        "evidence_ratio_weaken": DEFAULT_CONFIG.evidence_ratio_weaken,
    }
    return {**body, "issued_at": issued_at, "hash": sha256_hex(canonical_json(body))}


def verify_preregistration(prereg: dict) -> bool:
    body = {k: v for k, v in prereg.items() if k not in ("hash", "issued_at")}
    return sha256_hex(canonical_json(body)) == prereg.get("hash")


def score_frozen(model: dict, panel: Panel, start: date, end: date, cfg: EngineConfig = DEFAULT_CONFIG,
                 keep_days: int = 40) -> dict:
    """Score a frozen model on outcome days in [start, end] using only information available before each day."""
    x, y = panel.variables.get(model["exposure"]), panel.variables.get(model["outcome"])
    if x is None or y is None:
        return {"scored_days": 0, "reason": "variables_missing"}
    lag, sigma, beta, sd_x = model["lag"], model["sigma"], model["beta"], model["sd_x"]
    wd_off = model["weekday_offsets"]
    llr = 0.0
    scored = informative = hits = misses = 0
    inside = 0
    se_model = se_null = 0.0
    days = []
    for t, d in enumerate(panel.dates):
        if d < start or d > end or np.isnan(y[t]):
            continue
        s = t - lag
        if s < 1 or np.isnan(x[s]):
            continue
        y_base = _trailing_mean(y, t, model["y_window_days"], Y_MIN_OBS)
        x_base = _trailing_mean(x, s, model["x_window_days"], X_MIN_OBS)
        if y_base is None or x_base is None:
            continue
        mu0 = y_base + wd_off[int(panel.weekdays[t])]
        dx = float(x[s] - x_base)
        shift = beta * dx
        mu1 = mu0 + shift
        yy = float(y[t])
        llr += ((yy - mu0) ** 2 - (yy - mu1) ** 2) / (2.0 * sigma * sigma)
        se_model += (yy - mu1) ** 2
        se_null += (yy - mu0) ** 2
        inside += int(abs(yy - mu1) <= 1.2816 * sigma)
        scored += 1
        if abs(dx) >= model["informative_sd_multiple"] * sd_x:
            informative += 1
            if (yy - mu0) * shift > 0:
                hits += 1
            elif (yy - mu0) * shift < 0:
                misses += 1
        if len(days) < keep_days:
            days.append({"date": d.isoformat(), "y": yy, "mu_null": mu0, "mu_model": mu1, "exposure_dev": dx})
    out = {
        "scored_days": scored, "informative_days": informative, "hits": hits, "misses": misses,
        "llr_sum": float(llr), "evidence_ratio": float(math.exp(max(-50.0, min(50.0, llr)))),
        "coverage_80": (inside / scored) if scored else None,
        "mse_model": (se_model / scored) if scored else None, "mse_null": (se_null / scored) if scored else None,
        "skill": (1.0 - se_model / se_null) if scored and se_null > 0 else None,
        "start": start.isoformat(), "end": end.isoformat(), "days": days,
    }
    return out


def horizon_verdict(score: dict, cfg: EngineConfig = DEFAULT_CONFIG) -> str:
    """Per-horizon verdict used for the legacy hit/miss tallies."""
    if score.get("scored_days", 0) < cfg.forecast_min_scored_days:
        return "INCONCLUSIVE"
    er = score["evidence_ratio"]
    if er >= 3.0:
        return "SUPPORTED"
    if er <= 1.0 / 3.0:
        return "WEAKENED"
    return "INCONCLUSIVE"


def hit_rate_posterior(hits: int, misses: int) -> dict:
    """Beta(1,1) posterior for the informative-day hit rate; P(rate > 0.5) tests 'better than a coin flip'."""
    a, b = 1.0 + hits, 1.0 + misses
    return {"alpha": a, "beta": b, "mean": a / (a + b), "p_gt_half": 1.0 - beta_cdf(0.5, a, b)}


def summarize_track(scores: list, cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Combine completed forward-test scores for one hypothesis into the track record used by the gates."""
    done = [s for s in scores if s and s.get("scored_days", 0) > 0]
    llr = sum(s["llr_sum"] for s in done)
    hits = sum(s["hits"] for s in done)
    misses = sum(s["misses"] for s in done)
    post = hit_rate_posterior(hits, misses)
    return {
        "forecasts_completed": len(done), "scored_days": sum(s["scored_days"] for s in done),
        "informative_days": sum(s["informative_days"] for s in done), "hits": hits, "misses": misses,
        "llr_sum": float(llr), "evidence_ratio": float(math.exp(max(-50.0, min(50.0, llr)))),
        "hit_rate": post["mean"], "p_hit_rate_gt_half": post["p_gt_half"],
        "interpretation": ("confirmed" if math.exp(max(-50.0, min(50.0, llr))) >= cfg.evidence_ratio_confirm
                           else "weakened" if math.exp(max(-50.0, min(50.0, llr))) <= cfg.evidence_ratio_weaken
                           else "accumulating"),
    }
