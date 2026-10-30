"""Statistical process control for personal baselines (robust level, EWMA, CUSUM).

Replaces ad-hoc "7-day average vs 21-day average" comparisons with charts whose false
alarm behaviour is known. Scale is estimated robustly (median / MAD) and widened for
serial correlation so that autocorrelated self-report data does not raise constant alarms.
"""
from __future__ import annotations

import math

import numpy as np

from .config import DEFAULT_CONFIG, EngineConfig


def _mad_scale(x: np.ndarray) -> float:
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med))) * 1.4826
    if mad > 0:
        return mad
    sd = float(x.std(ddof=1)) if len(x) > 1 else 0.0
    return sd


def analyze_drift(values: np.ndarray, dates: list, cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Detect a sustained recent shift in one daily series. ``values`` has NaN for missing days."""
    T = len(values)
    obs = ~np.isnan(values)
    n_obs = int(obs.sum())
    base_end = T - cfg.drift_recent_days
    out: dict = {"evaluable": False, "n_observed": n_obs}
    if n_obs < cfg.drift_min_days or base_end < 7:
        out["reason"] = "too_few_observations"
        return out
    base_mask = obs.copy()
    base_mask[base_end:] = False
    if int(base_mask.sum()) < 10:
        out["reason"] = "baseline_too_short"
        return out
    base = values[base_mask]
    center = float(np.median(base))
    scale = _mad_scale(base)
    if scale <= 1e-9:
        out["reason"] = "constant_baseline"
        return out
    # serial-correlation widening of the level-chart scale (bounded)
    rho = 0.0
    b = np.where(base_mask, values, np.nan)
    a1, a2 = b[:-1], b[1:]
    mm = ~(np.isnan(a1) | np.isnan(a2))
    if mm.sum() >= 8:
        u, v = a1[mm] - a1[mm].mean(), a2[mm] - a2[mm].mean()
        den = math.sqrt(float(u @ u) * float(v @ v))
        rho = float(u @ v / den) if den > 0 else 0.0
    rho = min(0.6, max(0.0, rho))
    sigma = scale * math.sqrt((1.0 + rho) / (1.0 - rho))
    z = (values - center) / sigma

    k, h = cfg.cusum_k, cfg.cusum_h
    cu_up = np.zeros(T)
    cu_dn = np.zeros(T)
    up = dn = 0.0
    onset_up = onset_dn = None
    ewma = np.full(T, np.nan)
    lam = cfg.ewma_lambda
    e = 0.0
    seen = 0
    ewma_alarm = []
    for t in range(T):
        if np.isnan(z[t]):
            cu_up[t], cu_dn[t] = up, dn
            continue
        up = max(0.0, up + z[t] - k)
        dn = max(0.0, dn - z[t] - k)
        cu_up[t], cu_dn[t] = up, dn
        seen += 1
        e = lam * z[t] + (1 - lam) * e
        ewma[t] = e
        lim = cfg.ewma_L * math.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * seen)))
        if abs(e) > lim:
            ewma_alarm.append(t)
    recent = slice(base_end, T)
    cusum_alarm = bool((cu_up[recent] > h).any() or (cu_dn[recent] > h).any())
    direction = None
    onset_idx = None
    if cusum_alarm:
        arr, direction = (cu_up, "higher") if cu_up[recent].max() >= cu_dn[recent].max() else (cu_dn, "lower")
        peak = base_end + int(np.argmax(arr[recent]))
        i = peak
        while i > 0 and arr[i] > 0:
            i -= 1
        onset_idx = min(peak, i + 1)
    out.update({
        "evaluable": True, "baseline_center": center, "baseline_scale": scale, "serial_corr_rho": rho,
        "effective_sigma": sigma, "cusum_k": k, "cusum_h": h, "ewma_lambda": lam,
        "recent_days": cfg.drift_recent_days,
        "shift_detected": cusum_alarm,
        "ewma_alarm_recent": bool(any(t >= base_end for t in ewma_alarm)),
    })
    if cusum_alarm and onset_idx is not None:
        seg = values[onset_idx:]
        seg = seg[~np.isnan(seg)]
        out["onset_date"] = dates[onset_idx].isoformat()
        out["direction"] = direction
        out["shift_size"] = float(np.mean(seg) - center) if len(seg) else None
        out["shift_size_sigma"] = float((np.mean(seg) - center) / sigma) if len(seg) else None
        out["days_since_onset"] = int(T - 1 - onset_idx)
    # complementary recent-window mean test (more sensitive to short, large shifts than CUSUM)
    rec = values[base_end:]
    rec = rec[~np.isnan(rec)]
    if len(rec) >= 3:
        se_mean = sigma / math.sqrt(len(rec))
        zr = (float(rec.mean()) - center) / se_mean
        out["recent_window"] = {"n": int(len(rec)), "mean": float(rec.mean()), "z": float(zr),
                                "notable": bool(abs(zr) >= 2.5 and abs(rec.mean() - center) >= 0.5 * scale),
                                "direction": "higher" if rec.mean() > center else "lower"}
    # single-day extremes (modified z-score of Iglewicz & Hoaglin)
    robust_z = 0.6745 * (values - center) / (scale if scale > 0 else 1.0)
    ext = [dates[i].isoformat() for i in range(T) if not np.isnan(robust_z[i]) and abs(robust_z[i]) > 3.5 and i >= base_end]
    out["extreme_recent_days"] = ext
    out["latest_value"] = float(values[~np.isnan(values)][-1])
    out["latest_z"] = float((out["latest_value"] - center) / sigma)
    return out
