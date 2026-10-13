"""Calibrated inference for personal daily time series.

What is different from a plain correlation scan
  * Both series are adjusted for weekday structure and linear trend first
    (Frisch-Waugh-Lovell: the partial correlation equals the covariate-adjusted slope).
  * The null distribution is *empirical*: the other series is circularly shifted to
    alignments far away from every hypothesised lag, which preserves autocorrelation,
    heaping and gap patterns. Its spread calibrates a continuous p-value and the CI.
  * A second, parametric opinion (Newey-West HAC) is computed; the reported p-value is
    the larger (more conservative) of the two. Claiming evidence requires both to agree.
  * Nothing is imputed. Gaps stay NaN on a calendar grid and lags are calendar lags.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np

from .config import DEFAULT_CONFIG, EngineConfig
from .special import fisher_z, norm_ppf, t_ppf, t_two_sided_p

NAN = float("nan")


# --------------------------------------------------------------------------- #
# Small numeric helpers
# --------------------------------------------------------------------------- #
def build_design(ordinals: np.ndarray, weekdays: np.ndarray) -> np.ndarray:
    """Intercept, centred linear trend, and six weekday indicators (Monday = reference)."""
    T = len(ordinals)
    t = (ordinals - ordinals.mean()) / max(1.0, float(T))
    cols = [np.ones(T), t] + [(weekdays == k).astype(float) for k in range(1, 7)]
    return np.column_stack(cols)


def residualize(v: np.ndarray, D: np.ndarray, min_rows_per_col: float = 1.5) -> np.ndarray:
    """Residuals of ``v`` on design ``D`` fitted on observed rows only (NaN preserved).

    When there are too few observations for the full design the weekday dummies are
    dropped (intercept + trend only); with fewer than 6 observations NaNs are returned.
    """
    out = np.full_like(v, np.nan, dtype=float)
    m = ~np.isnan(v)
    n = int(m.sum())
    if n < 6:
        return out
    cols = D.shape[1]
    X = D[m]
    if n < cols * min_rows_per_col + 2:
        X = X[:, :2]
    beta, *_ = np.linalg.lstsq(X, v[m], rcond=None)
    out[m] = v[m] - X @ beta
    return out


def rank_avg(x: np.ndarray) -> np.ndarray:
    """Average ranks (1-based) of a finite 1-D array."""
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    new = np.concatenate(([True], xs[1:] != xs[:-1]))
    grp = np.cumsum(new) - 1
    counts = np.bincount(grp)
    ends = np.cumsum(counts)
    starts = ends - counts
    avg = (starts + ends + 1) / 2.0
    ranks = np.empty(len(x))
    ranks[order] = avg[grp]
    return ranks


def rank_grid(v: np.ndarray) -> np.ndarray:
    out = np.full_like(v, np.nan, dtype=float)
    m = ~np.isnan(v)
    if m.sum() >= 3:
        out[m] = rank_avg(v[m])
    return out


def rolling_median_highpass(v: np.ndarray, window: int = 15, min_obs: int = 5) -> np.ndarray:
    """Value minus centred rolling median over observed days (NaN where unsupported)."""
    T = len(v)
    half = window // 2
    out = np.full(T, np.nan)
    for t in range(T):
        if np.isnan(v[t]):
            continue
        seg = v[max(0, t - half): t + half + 1]
        seg = seg[~np.isnan(seg)]
        if len(seg) >= min_obs:
            out[t] = v[t] - float(np.median(seg))
    return out


def corr_masked(a: np.ndarray, b: np.ndarray):
    """Pearson r on jointly observed entries. Returns (r, n)."""
    m = ~(np.isnan(a) | np.isnan(b))
    n = int(m.sum())
    if n < 3:
        return NAN, n
    x, y = a[m] - a[m].mean(), b[m] - b[m].mean()
    den = math.sqrt(float(x @ x) * float(y @ y))
    if den <= 0.0:
        return NAN, n
    return float(x @ y) / den, n


def pair_arrays(rx: np.ndarray, ry: np.ndarray, lag: int):
    """Calendar-lag pairing: x[t] with y[t+lag]. Returns (x, y, idx_of_x_day)."""
    T = len(rx)
    a, b = rx[: T - lag], ry[lag:]
    m = ~(np.isnan(a) | np.isnan(b))
    return a[m], b[m], np.flatnonzero(m)


def acf_grid(v: np.ndarray, maxlag: int) -> np.ndarray:
    """Pairwise-available autocorrelations at lags 1..maxlag on a gappy grid."""
    out = np.zeros(maxlag)
    for h in range(1, maxlag + 1):
        r, n = corr_masked(v[:-h], v[h:])
        out[h - 1] = 0.0 if (math.isnan(r) or n < 6) else r
    return out


def bartlett_effective_n(rx: np.ndarray, ry: np.ndarray, n: int) -> float:
    """Bartlett/Bayley-Hammersley effective sample size from the series' autocorrelations."""
    if n < 8:
        return float(n)
    m = max(1, min(int(round(n ** (1 / 3))) + 1, n // 4))
    ax, ay = acf_grid(rx, m), acf_grid(ry, m)
    w = 1.0 - np.arange(1, m + 1) / (m + 1.0)
    s = 1.0 + 2.0 * float(np.sum(w * ax * ay))
    return float(min(n, max(3.0, n / max(s, 0.25))))


# --------------------------------------------------------------------------- #
# HAC (Newey-West) test for the adjusted slope
# --------------------------------------------------------------------------- #
@dataclass
class HacResult:
    beta: float
    se: float
    t: float
    p: float
    n: int
    bandwidth: int


def hac_slope_test(rx: np.ndarray, ry: np.ndarray, lag: int) -> Optional[HacResult]:
    """OLS slope of y[t+lag] on x[t] with a Bartlett-kernel HAC variance on a gappy grid."""
    T = len(rx)
    a, b = rx[: T - lag], ry[lag:]
    m = ~(np.isnan(a) | np.isnan(b))
    n = int(m.sum())
    if n < 8:
        return None
    ac = np.where(m, a - a[m].mean(), 0.0)
    bc = np.where(m, b - b[m].mean(), 0.0)
    sxx = float(ac @ ac)
    if sxx <= 0:
        return None
    beta = float(ac @ bc) / sxx
    e = np.where(m, bc - beta * ac, 0.0)
    u = ac * e
    bw = max(2, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))
    bw = min(bw, max(2, n // 4))
    omega = float(u @ u)
    for h in range(1, bw + 1):
        omega += 2.0 * (1.0 - h / (bw + 1.0)) * float(u[:-h] @ u[h:])
    var_beta = max(omega, 0.0) / (sxx * sxx) * (n / max(1.0, n - 2.0))
    if var_beta <= 0:
        return None
    se = math.sqrt(var_beta)
    t = beta / se
    return HacResult(beta, se, t, t_two_sided_p(abs(t), n - 2), n, bw)


# --------------------------------------------------------------------------- #
# Empirical (circular-shift) null
# --------------------------------------------------------------------------- #
class NullKernel:
    """Precomputed shift offsets/indices shared by all candidates on one grid."""

    def __init__(self, T: int, max_lag: int, buffer: int):
        self.T = T
        lo, hi = max_lag + buffer + 1, T - buffer
        self.ks = np.arange(lo, hi) if hi > lo else np.array([], dtype=int)
        self.idx = (np.arange(T)[None, :] + self.ks[:, None]) % T if len(self.ks) else np.zeros((0, T), dtype=int)

    @property
    def n_shifts(self) -> int:
        return len(self.ks)


def shift_null_z(x0: np.ndarray, mx: np.ndarray, y0: np.ndarray, my: np.ndarray, kernel: NullKernel, min_pairs: int):
    """Fisher-z * sqrt(n-3) statistics of x against y circularly shifted by every kernel offset.

    ``x0``/``y0`` are NaN-zeroed arrays and ``mx``/``my`` float masks (1.0 observed).
    """
    if kernel.n_shifts == 0:
        return np.array([])
    Y = y0[kernel.idx]
    M = my[kernel.idx] * mx[None, :]
    n = M.sum(axis=1)
    sx = M @ x0
    sxx = M @ (x0 * x0)
    My = M * Y
    sy = My.sum(axis=1)
    syy = (My * Y).sum(axis=1)
    sxy = My @ x0
    with np.errstate(divide="ignore", invalid="ignore"):
        cov = n * sxy - sx * sy
        den = np.sqrt((n * sxx - sx * sx) * (n * syy - sy * sy))
        r = cov / den
    ok = (n >= min_pairs) & np.isfinite(r)
    r = np.clip(r[ok], -0.999999, 0.999999)
    return np.arctanh(r) * np.sqrt(n[ok] - 3.0)


def effective_shifts(zs: np.ndarray, max_lag: int = 10) -> float:
    """Effective number of independent draws among the ordered shift-null statistics.

    Neighbouring shifts of an autocorrelated series are correlated, so the S shifts carry
    fewer than S independent pieces of information about the null's spread. This is
    measured directly from the null sequence's own positive autocorrelation.
    """
    S = len(zs)
    z = zs - zs.mean()
    den = float(z @ z)
    if S < 8 or den <= 0:
        return float(S)
    H = max(1, min(max_lag, S // 4))
    s = 1.0
    for h in range(1, H + 1):
        rho = float(z[:-h] @ z[h:]) / den
        if rho <= 0:
            break
        s += 2.0 * rho * (1.0 - h / (H + 1.0))
    return max(4.0, S / s)


@dataclass
class PreparedVar:
    name: str
    raw: np.ndarray
    resid: np.ndarray
    rank_resid: np.ndarray
    highpass: np.ndarray
    x0: np.ndarray
    mask: np.ndarray
    sd_resid: float
    sd_raw: float
    acf1: Optional[float]


def prepare_variable(name: str, raw: np.ndarray, D: np.ndarray, cfg: EngineConfig = DEFAULT_CONFIG) -> PreparedVar:
    resid = residualize(raw, D)
    rres = residualize(rank_grid(raw), D)
    m = ~np.isnan(resid)
    sd_res = float(np.nanstd(resid, ddof=1)) if m.sum() > 2 else 0.0
    obs = raw[~np.isnan(raw)]
    sd_raw = float(obs.std(ddof=1)) if len(obs) > 2 else 0.0
    ac = acf_grid(resid, 1)[0] if m.sum() >= 8 else None
    return PreparedVar(
        name=name, raw=raw, resid=resid, rank_resid=rres,
        highpass=rolling_median_highpass(raw, cfg.highpass_window),
        x0=np.where(m, resid, 0.0), mask=m.astype(float), sd_resid=sd_res, sd_raw=sd_raw, acf1=ac,
    )


# --------------------------------------------------------------------------- #
# Pair screening statistic (computed for every candidate in the family)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4096)
def _cached_t_crit(p: float, df: float) -> float:
    return t_ppf(p, df)


@dataclass
class PairScreen:
    lag: int
    n: int
    r_raw: float
    r_adj: float
    z_obs: float
    p_hac: Optional[float]
    p_eff: float
    p_shift_gauss: Optional[float]
    p_shift_rank: Optional[float]
    p_combined: float
    rms_null: Optional[float]
    n_shifts: int
    n_eff: float
    n_eff_bartlett: float
    se_z: float
    ci_z_crit: float
    beta: float
    sd_x_resid: float
    sd_y_resid: float
    p_method: str
    df_null: float = 30.0
    day_idx: Optional[np.ndarray] = field(default=None, repr=False)

    def r_ci(self, level: float = 0.95):
        """Fisher-z interval using the shift-calibrated standard error and t reference."""
        z = fisher_z(self.r_adj)
        crit = _cached_t_crit(round(0.5 + level / 2.0, 6), round(max(4.0, self.df_null), 1))
        return math.tanh(z - crit * self.se_z), math.tanh(z + crit * self.se_z)


def screen_pair(px: PreparedVar, py: PreparedVar, lag: int, kernel: NullKernel, cfg: EngineConfig = DEFAULT_CONFIG) -> Optional[PairScreen]:
    T = len(px.resid)
    a, b, idx = pair_arrays(px.resid, py.resid, lag)
    n = len(a)
    if n < cfg.min_pairs:
        return None
    r_adj, _ = corr_masked(px.resid[: T - lag], py.resid[lag:])
    if math.isnan(r_adj):
        return None
    r_raw, _ = corr_masked(px.raw[: T - lag], py.raw[lag:])
    z_obs = fisher_z(r_adj) * math.sqrt(max(1.0, n - 3.0))

    hac = hac_slope_test(px.resid, py.resid, lag) if cfg.use_hac else None
    n_eff_b = bartlett_effective_n(px.resid, py.resid, n)
    p_eff = t_two_sided_p(abs(r_adj) * math.sqrt(max(1.0, (n_eff_b - 2.0)) / max(1e-12, 1.0 - r_adj * r_adj)), max(1.0, n_eff_b - 2.0))

    zs = shift_null_z(px.x0, px.mask, py.x0, py.mask, kernel, min_pairs=max(8, int(0.5 * n)))
    p_gauss = p_rank = rms = None
    df_null = 30.0
    if len(zs) >= cfg.min_shifts:
        rms = max(1.0, float(math.sqrt(np.mean(zs * zs))))
        df_null = max(4.0, effective_shifts(zs, cfg.null_acf_max_lag) - 1.0)
        p_gauss = t_two_sided_p(abs(z_obs) / rms, df_null)
        p_rank = (1.0 + float(np.sum(np.abs(zs) >= abs(z_obs)))) / (1.0 + len(zs))

    parts = {"HAC": hac.p if hac else None, "Bartlett-effN": p_eff, "shift-calibrated": p_gauss}
    avail = {k: v for k, v in parts.items() if v is not None}
    p_comb = max(avail.values())
    method = "max(" + ", ".join(avail) + ")"
    if rms is not None:
        se_z = rms / math.sqrt(max(1.0, n - 3.0))
    else:
        se_z = 1.0 / math.sqrt(max(1.0, n_eff_b - 3.0))
    n_eff = min(float(n), 3.0 + 1.0 / (se_z * se_z))
    sx, sy = px.sd_resid, py.sd_resid
    beta = r_adj * sy / sx if sx > 0 else NAN
    ps_obj = PairScreen(
        lag=lag, n=n, r_raw=r_raw, r_adj=r_adj, z_obs=z_obs,
        p_hac=hac.p if hac else None, p_eff=p_eff, p_shift_gauss=p_gauss, p_shift_rank=p_rank,
        p_combined=float(min(1.0, max(0.0, p_comb))), rms_null=rms, n_shifts=len(zs), n_eff=n_eff,
        n_eff_bartlett=n_eff_b, se_z=se_z, ci_z_crit=0.0, beta=beta,
        sd_x_resid=sx, sd_y_resid=sy, p_method=method, df_null=df_null, day_idx=idx,
    )
    return ps_obj


# --------------------------------------------------------------------------- #
# Robustness diagnostics (run on candidates that could reach a claim)
# --------------------------------------------------------------------------- #
def _same_sign(a: Optional[float], b: Optional[float], tol: float = 1e-12) -> bool:
    return a is not None and b is not None and not math.isnan(a) and not math.isnan(b) and (abs(a) < tol or abs(b) < tol or a * b > 0)


def block_bootstrap_ci(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, B: int = 1000, level: float = 0.90):
    """Moving-block bootstrap percentile interval for Pearson r of time-ordered pairs."""
    n = len(a)
    if n < 12:
        return None
    ell = int(min(10, max(2, math.ceil(1.5 * n ** (1 / 3)))))
    nblocks = int(math.ceil(n / ell))
    starts = rng.integers(0, n - ell + 1, size=(B, nblocks))
    idx = (starts[:, :, None] + np.arange(ell)[None, None, :]).reshape(B, -1)[:, :n]
    xa, yb = a[idx], b[idx]
    xa = xa - xa.mean(axis=1, keepdims=True)
    yb = yb - yb.mean(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (xa * yb).sum(axis=1) / np.sqrt((xa * xa).sum(axis=1) * (yb * yb).sum(axis=1))
    r = r[np.isfinite(r)]
    if len(r) < B // 2:
        return None
    lo, hi = np.quantile(r, [(1 - level) / 2.0, 1 - (1 - level) / 2.0])
    return float(lo), float(hi), ell


def robustness(px: PreparedVar, py: PreparedVar, scr: PairScreen, week_ids: np.ndarray, rng: np.random.Generator,
               cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Sensitivity of the adjusted association to analytic choices and influential data."""
    T = len(px.resid)
    lag = scr.lag
    a, b, idx = pair_arrays(px.resid, py.resid, lag)
    n = len(a)
    r = scr.r_adj
    out: dict = {"n": n}

    rho, _ = corr_masked(px.rank_resid[: T - lag], py.rank_resid[lag:])
    out["spearman_adj_rho"] = None if math.isnan(rho) else rho

    def wins(v):
        lo, hi = np.quantile(v, [cfg.winsor_q, 1 - cfg.winsor_q])
        return np.clip(v, lo, hi)
    rw, _ = corr_masked(wins(a), wins(b))
    out["winsorized_r"] = None if math.isnan(rw) else rw

    loo = []
    if n >= 9:
        for i in range(n):
            keep = np.ones(n, dtype=bool)
            keep[i] = False
            rr, _ = corr_masked(a[keep], b[keep])
            if not math.isnan(rr):
                loo.append(rr)
    out["loo_r_min"] = float(min(loo)) if loo else None
    out["loo_r_max"] = float(max(loo)) if loo else None
    out["loo_sign_stable"] = bool(loo) and all(_same_sign(r, v) for v in loo)

    wk = week_ids[idx]
    uniq = np.unique(wk)
    lw = []
    if len(uniq) >= 3:
        for w in uniq:
            keep = wk != w
            if keep.sum() >= 8:
                rr, _ = corr_masked(a[keep], b[keep])
                if not math.isnan(rr):
                    lw.append(rr)
    out["leave_week_r_min"] = float(min(lw)) if lw else None
    out["leave_week_r_max"] = float(max(lw)) if lw else None
    out["leave_week_sign_stable"] = bool(lw) and all(_same_sign(r, v) for v in lw)

    rh, nh = corr_masked(px.highpass[: T - lag], py.highpass[lag:])
    out["highpass_r"] = None if (math.isnan(rh) or nh < 10) else rh

    out["raw_r"] = None if math.isnan(scr.r_raw) else scr.r_raw

    if n >= 20:
        h = n // 2
        r1, _ = corr_masked(a[:h], b[:h])
        r2, _ = corr_masked(a[h:], b[h:])
        out["split_half_r"] = [None if math.isnan(r1) else r1, None if math.isnan(r2) else r2]
        out["split_half_sign_stable"] = _same_sign(r1, r) and _same_sign(r2, r)
    else:
        out["split_half_r"] = None
        out["split_half_sign_stable"] = None

    bs = block_bootstrap_ci(a, b, rng, cfg.bootstrap_resamples, cfg.bootstrap_ci_level)
    if bs is not None:
        out["bootstrap_ci"] = [bs[0], bs[1]]
        out["bootstrap_level"] = cfg.bootstrap_ci_level
        out["bootstrap_block_len"] = bs[2]
        out["bootstrap_excludes_zero"] = bool(bs[0] > 0 or bs[1] < 0)
    else:
        out["bootstrap_ci"] = None
        out["bootstrap_excludes_zero"] = None

    sign_ok = [
        _same_sign(r, rho), _same_sign(r, rw), out["loo_sign_stable"], out["leave_week_sign_stable"] if lw else True,
        _same_sign(r, out["highpass_r"]) if out["highpass_r"] is not None else True,
    ]
    magnitude_ok = (rw is not None and not math.isnan(rw) and abs(rw - r) <= 0.25)
    out["sign_consistent"] = bool(all(sign_ok))
    out["outlier_stable"] = bool(magnitude_ok and out["loo_sign_stable"])
    out["robust"] = bool(
        out["sign_consistent"] and out["outlier_stable"]
        and (out["bootstrap_excludes_zero"] is not False)
        and (out["split_half_sign_stable"] is not False)
        and not math.isnan(rho) and abs(rho) >= max(0.15, 0.5 * abs(r))
    )
    return out


# --------------------------------------------------------------------------- #
# Directional (Granger-style) test with AR control, plus its reverse
# --------------------------------------------------------------------------- #
def _partial_r(cols_y: np.ndarray, cols_x: np.ndarray, Z: np.ndarray):
    """Partial correlation of y and x given Z (rows already complete)."""
    n = len(cols_y)
    if n < Z.shape[1] + 6:
        return NAN, n
    by, *_ = np.linalg.lstsq(Z, cols_y, rcond=None)
    bx, *_ = np.linalg.lstsq(Z, cols_x, rcond=None)
    ey, ex = cols_y - Z @ by, cols_x - Z @ bx
    den = math.sqrt(float(ey @ ey) * float(ex @ ex))
    if den <= 0:
        return NAN, n
    return float(ey @ ex) / den, n


def _ar_partial(x: np.ndarray, y: np.ndarray, D: np.ndarray, lag: int):
    """Partial r of y[t] and x[t-lag] controlling for D[t] and y[t-1] (complete cases)."""
    T = len(y)
    t0 = max(lag, 1)
    yt, ylag, xl = y[t0:], y[t0 - 1: T - 1], x[t0 - lag: T - lag]
    m = ~(np.isnan(yt) | np.isnan(ylag) | np.isnan(xl))
    if m.sum() < D.shape[1] + 10:
        return NAN, int(m.sum())
    Z = np.column_stack([D[t0:][m], ylag[m]])
    return _partial_r(yt[m], xl[m], Z)


def ar_controlled_test(x: np.ndarray, y: np.ndarray, D: np.ndarray, lag: int, kernel: NullKernel, cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Does x[t-lag] add information about y[t] beyond y's own recent history and calendar effects?

    The p-value comes from the same far-shift empirical null: x is circularly shifted
    relative to (y, y[t-1], calendar), the AR-controlled partial correlation recomputed,
    and the observed value located within that null's spread.
    """
    r_obs, n = _ar_partial(x, y, D, lag)
    if math.isnan(r_obs) or kernel.n_shifts < cfg.min_shifts:
        return {"evaluable": False, "n": n}
    q = D.shape[1] + 1
    z_obs = fisher_z(r_obs) * math.sqrt(max(1.0, n - q - 2.0))
    zs = []
    for k in kernel.ks:
        xs = np.roll(x, int(k))
        rr, nn = _ar_partial(xs, y, D, lag)
        if not math.isnan(rr) and nn > q + 8:
            zs.append(fisher_z(rr) * math.sqrt(max(1.0, nn - q - 2.0)))
    if len(zs) < cfg.min_shifts:
        return {"evaluable": False, "n": n}
    zs = np.array(zs)
    rms = max(1.0, float(math.sqrt(np.mean(zs * zs))))
    df_null = max(4.0, effective_shifts(zs, cfg.null_acf_max_lag) - 1.0)
    return {
        "evaluable": True, "n": n, "r_partial": r_obs, "z_obs": z_obs, "rms_null": rms,
        "p": t_two_sided_p(abs(z_obs) / rms, df_null), "n_shifts": len(zs),
    }


def direction_verdict(fwd: dict, rev: dict, cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Decide whether the forward (x -> y) lagged evidence supports a direction, given the reverse test.

    Ordering is a stronger claim than association, so the forward test must clear the stricter
    ``directional_alpha`` while the reverse test is held to the looser ``reverse_alpha``.
    """
    out: dict = {}
    if not fwd.get("evaluable"):
        return out
    asym = None
    if rev.get("evaluable"):
        asym = abs(fwd["r_partial"]) - abs(rev["r_partial"])
    fwd_sig = fwd["p"] <= cfg.directional_alpha
    rev_sig = bool(rev.get("evaluable")) and rev["p"] <= cfg.reverse_alpha
    out["asymmetry"] = asym
    out["forward_significant"] = fwd_sig
    out["reverse_significant"] = rev_sig
    out["direction_supported"] = bool(fwd_sig and (not rev_sig or (asym is not None and asym > 0.05)))
    return out


def directional_diagnostics(px: PreparedVar, py: PreparedVar, D: np.ndarray, lag: int, kernel: NullKernel,
                            cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    """Forward (x -> y) and reverse (y -> x) AR-controlled lagged tests for lag >= 1."""
    if lag < 1:
        return {"evaluable": False, "reason": "contemporaneous_pair_direction_not_identifiable"}
    fwd = ar_controlled_test(px.raw, py.raw, D, lag, kernel, cfg)
    rev = ar_controlled_test(py.raw, px.raw, D, lag, kernel, cfg)
    out = {"evaluable": bool(fwd.get("evaluable")), "forward": fwd, "reverse": rev}
    out.update(direction_verdict(fwd, rev, cfg))
    return out


# --------------------------------------------------------------------------- #
# Sensitivity to unmeasured confounding, power and sufficiency
# --------------------------------------------------------------------------- #
def e_value(effect_std: float, ci_std: Optional[tuple] = None) -> dict:
    """E-value (VanderWeele & Ding 2017) for a standardised continuous effect.

    Uses the approximation RR ~ exp(0.91 d) applied to the adjusted standardised slope per
    1 SD of exposure (d = r_adj). The E-value is the minimum strength of association, on
    the risk-ratio scale, that an unmeasured confounder would need with *both* exposure
    and outcome to fully explain the association. It is a sensitivity analysis, not a test.
    """
    def _ev(d: float) -> float:
        rr = math.exp(0.91 * abs(d))
        return rr + math.sqrt(rr * (rr - 1.0))
    point = _ev(effect_std)
    ci_val = 1.0
    if ci_std is not None:
        lo, hi = ci_std
        if lo > 0 or hi < 0:
            ci_val = _ev(lo if lo > 0 else hi)
    return {"e_value": point, "e_value_ci": ci_val, "approximation": "RR~exp(0.91*d), d = adjusted slope per 1 SD exposure"}


def minimum_detectable_r(n_eff: float, alpha: float = 0.05, power: float = 0.80) -> Optional[float]:
    """Smallest |r| detectable with the given effective n at two-sided ``alpha`` and ``power``."""
    if n_eff <= 4:
        return None
    za = norm_ppf(1.0 - alpha / 2.0)
    zb = norm_ppf(power)
    return float(math.tanh((za + zb) / math.sqrt(n_eff - 3.0)))


def days_needed(r_target: float, n_eff_per_day: float, alpha: float = 0.05, power: float = 0.80) -> Optional[int]:
    """Calendar pair-days needed to detect |r_target| given the observed n_eff/n ratio."""
    r = abs(r_target)
    if r <= 0 or r >= 1 or n_eff_per_day <= 0:
        return None
    za = norm_ppf(1.0 - alpha / 2.0)
    zb = norm_ppf(power)
    n_eff_needed = ((za + zb) / math.atanh(r)) ** 2 + 3.0
    return int(math.ceil(n_eff_needed / max(0.05, min(1.0, n_eff_per_day))))
