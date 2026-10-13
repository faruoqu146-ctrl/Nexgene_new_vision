import math
from datetime import date, timedelta

import numpy as np

from _research_helpers import ROOT  # noqa: F401
from backend.app.research.config import DEFAULT_CONFIG as CFG
from backend.app.research.spc import analyze_drift

DATES = [date(2026, 1, 1) + timedelta(days=i) for i in range(90)]


def _ar(rng, n, phi):
    x = np.zeros(n + 50)
    for t in range(1, n + 50):
        x[t] = phi * x[t - 1] + math.sqrt(1 - phi * phi) * rng.standard_normal()
    return x[50:]


def _series(rng, shift_sd=0.0, last=0, miss=0.15, scale=1.2):
    v = 5 + _ar(rng, 90, 0.5) * scale
    if shift_sd:
        v[90 - last:] += shift_sd * scale
    v[rng.random(90) < miss] = np.nan
    return v


def test_stable_series_rarely_raise_alarms():
    rng = np.random.default_rng(1)
    alarms = sum(analyze_drift(_series(rng), DATES, CFG).get("shift_detected", False) for _ in range(300))
    assert alarms / 300 < 0.08


def test_large_sustained_shift_is_usually_detected():
    rng = np.random.default_rng(2)
    hits = 0
    for _ in range(200):
        r = analyze_drift(_series(rng, shift_sd=2.5, last=7), DATES, CFG)
        hits += bool(r.get("shift_detected") or r.get("recent_window", {}).get("notable"))
    assert hits / 200 > 0.6


def test_shift_report_has_direction_onset_and_size():
    rng = np.random.default_rng(3)
    v = 5 + _ar(rng, 90, 0.3)
    v[78:] += 6.0
    r = analyze_drift(v, DATES, CFG)
    assert r["shift_detected"] and r["direction"] == "higher" and r["shift_size"] > 3
    assert date.fromisoformat(r["onset_date"]) >= DATES[70] and r["days_since_onset"] <= 20


def test_downward_shift_is_reported_as_lower():
    rng = np.random.default_rng(4)
    v = 8 + _ar(rng, 90, 0.3)
    v[80:] -= 6.0
    r = analyze_drift(v, DATES, CFG)
    assert r["direction"] == "lower" and r["shift_size"] < -3


def test_constant_or_sparse_series_are_not_evaluable():
    assert analyze_drift(np.full(90, 5.0), DATES, CFG)["evaluable"] is False
    sparse = np.full(90, np.nan)
    sparse[:6] = [4, 5, 6, 5, 4, 6]
    assert analyze_drift(sparse, DATES, CFG)["evaluable"] is False


def test_extreme_recent_day_is_listed():
    rng = np.random.default_rng(5)
    v = 5 + _ar(rng, 90, 0.2) * 0.5
    v[88] = 15.0
    assert DATES[88].isoformat() in analyze_drift(v, DATES, CFG)["extreme_recent_days"]
