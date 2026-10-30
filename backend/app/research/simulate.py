"""Synthetic personal-data generators and validation studies.

Everything the engine claims about error control is measured here on data whose
ground truth is known. These studies are what the validation report is built from;
they say nothing about real-world performance on real people.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Optional, Sequence

import numpy as np

from .panel import Panel, panel_from_arrays


def _ar1(rng: np.random.Generator, T: int, phi: float, burn: int = 60) -> np.ndarray:
    e = rng.standard_normal(T + burn)
    x = np.zeros(T + burn)
    s = math.sqrt(max(1e-9, 1.0 - phi * phi))
    for t in range(1, T + burn):
        x[t] = phi * x[t - 1] + s * e[t]
    return x[burn:]


def simulate_panel(
    rng: np.random.Generator, *, T: int = 90, names: Optional[Sequence[str]] = None, n_vars: int = 6,
    ar: float = 0.5, weekly: float = 0.5, trend: float = 0.0, missing: float = 0.10,
    effects: Sequence[tuple] = (), round_scale: bool = False, start: date = date(2026, 1, 5),
    reverse_feedback: float = 0.0,
) -> Panel:
    """Simulate k variables with AR(1) noise, weekly seasonality, optional trend and planted effects.

    ``effects`` = [(x_name, y_name, lag, beta)]: y[t] += beta * z_x[t - lag] where z_x is the
    standardised x series. Missingness is completely at random per variable-day.
    """
    names = list(names) if names else [f"v{i}" for i in range(n_vars)]
    t = np.arange(T)
    z = {}
    for nm in names:
        base = _ar1(rng, T, ar)
        phase = rng.uniform(0, 2 * math.pi)
        season = weekly * np.sin(2 * math.pi * t / 7.0 + phase)
        tr = trend * rng.choice([-1.0, 1.0]) * (t - T / 2) / T
        z[nm] = base + season + tr
    out = {nm: z[nm].copy() for nm in names}
    for (xn, yn, lag, beta) in effects:
        zx = (z[xn] - z[xn].mean()) / z[xn].std()
        shifted = np.concatenate([np.zeros(lag), zx[: T - lag]]) if lag else zx
        out[yn] = out[yn] + beta * shifted
    if reverse_feedback:
        pass  # reserved
    arrays = {}
    for nm in names:
        v = out[nm]
        if round_scale:
            v = np.clip(np.round(5.0 + 1.6 * (v - v.mean()) / v.std()), 0, 10)
        miss = rng.random(T) < missing
        v = v.astype(float)
        v[miss] = np.nan
        arrays[nm] = v
    return panel_from_arrays(arrays, start)

