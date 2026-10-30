"""Special functions used by the research engine.

Pure-Python (stdlib only) implementations so the statistical core does not need
SciPy at runtime. Every function here is cross-checked against SciPy reference
values in ``backend/tests/test_research_special.py``.
"""
from __future__ import annotations

import math
from statistics import NormalDist

_STD_NORMAL = NormalDist()
_EPS = 3.0e-16
_FPMIN = 1.0e-300


def norm_cdf(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def norm_sf(x: float) -> float:
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def norm_ppf(p: float) -> float:
    """Inverse standard-normal CDF (Wichura AS241 via the standard library)."""
    if not 0.0 < p < 1.0:
        if p == 0.0:
            return -math.inf
        if p == 1.0:
            return math.inf
        raise ValueError("p must be in [0, 1]")
    return _STD_NORMAL.inv_cdf(p)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < _FPMIN:
        d = _FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = _FPMIN if abs(d) < _FPMIN else d
        c = 1.0 + aa / c
        c = _FPMIN if abs(c) < _FPMIN else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = _FPMIN if abs(d) < _FPMIN else d
        c = 1.0 + aa / c
        c = _FPMIN if abs(c) < _FPMIN else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < _EPS:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if a <= 0 or b <= 0:
        raise ValueError("a and b must be positive")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    front = math.exp(log_front)
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value of Student's t with ``df`` degrees of freedom."""
    if df <= 0 or math.isnan(t):
        return 1.0
    if math.isinf(t):
        return 0.0
    x = df / (df + t * t)
    return min(1.0, max(0.0, betainc(df / 2.0, 0.5, x)))


def t_sf(t: float, df: float) -> float:
    """One-sided upper-tail probability P(T > t)."""
    p2 = t_two_sided_p(abs(t), df)
    return 0.5 * p2 if t >= 0 else 1.0 - 0.5 * p2


def t_cdf(t: float, df: float) -> float:
    return 1.0 - t_sf(t, df)


def t_pdf(t: float, df: float) -> float:
    """Density of Student's t."""
    logc = math.lgamma((df + 1.0) / 2.0) - math.lgamma(df / 2.0) - 0.5 * math.log(df * math.pi)
    return math.exp(logc - (df + 1.0) / 2.0 * math.log1p(t * t / df))


def _t_ppf_bisect(p: float, df: float) -> float:
    sign = 1.0 if p > 0.5 else -1.0
    tail = 1.0 - p if p > 0.5 else p            # lower-tail mass, in (0, 0.5)
    lo, hi = 0.0, 1.0
    while t_sf(hi, df) > tail:
        hi *= 2.0
        if hi > 1e12:
            break
    for _ in range(200):                           # bisection to ~1e-15
        mid = 0.5 * (lo + hi)
        if t_sf(mid, df) > tail:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-14 * max(1.0, hi):
            break
    return sign * 0.5 * (lo + hi)


def t_ppf(p: float, df: float) -> float:
    """Quantile function of Student's t.

    Cornish-Fisher starting value (Abramowitz & Stegun 26.7.5) polished by Newton steps on the exact CDF;
    falls back to monotone bisection for very small df, extreme tails, or if Newton does not converge.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    if df > 1e6:
        return norm_ppf(p)
    if p == 0.5:
        return 0.0
    if df < 3.0 or p < 1e-7 or p > 1.0 - 1e-7:
        return _t_ppf_bisect(p, df)
    z = norm_ppf(p)
    z3, z5, z7 = z ** 3, z ** 5, z ** 7
    t = z + (z3 + z) / (4.0 * df) + (5.0 * z5 + 16.0 * z3 + 3.0 * z) / (96.0 * df ** 2) \
        + (3.0 * z7 + 19.0 * z5 + 17.0 * z3 - 15.0 * z) / (384.0 * df ** 3)
    for _ in range(12):
        step = (t_cdf(t, df) - p) / max(t_pdf(t, df), 1e-300)
        t -= step
        if abs(step) < 1e-13 * max(1.0, abs(t)):
            tail = min(p, 1.0 - p)
            if abs(t_cdf(t, df) - p) <= 1e-9 * tail + 1e-15:
                return t
            break
    return _t_ppf_bisect(p, df)


def f_sf(f: float, d1: float, d2: float) -> float:
    """Upper-tail probability of the F distribution."""
    if f <= 0.0:
        return 1.0
    x = d2 / (d2 + d1 * f)
    return min(1.0, max(0.0, betainc(d2 / 2.0, d1 / 2.0, x)))


def fisher_z(r: float) -> float:
    r = max(-0.999999, min(0.999999, r))
    return math.atanh(r)


def inv_fisher_z(z: float) -> float:
    return math.tanh(z)


def normal_pdf(x: float, mean: float = 0.0, sd: float = 1.0) -> float:
    if sd <= 0:
        return 0.0
    z = (x - mean) / sd
    return math.exp(-0.5 * z * z) / (sd * math.sqrt(2.0 * math.pi))


def log_normal_pdf(x: float, mean: float, sd: float) -> float:
    if sd <= 0:
        return -math.inf
    z = (x - mean) / sd
    return -0.5 * z * z - math.log(sd) - 0.5 * math.log(2.0 * math.pi)


def beta_cdf(x: float, a: float, b: float) -> float:
    return betainc(a, b, x)
