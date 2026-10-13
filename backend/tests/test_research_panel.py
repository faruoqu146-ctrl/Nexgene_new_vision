import math
from datetime import timedelta
from types import SimpleNamespace

import numpy as np

from _research_helpers import obs, utc
from backend.app.research.panel import build_panel, panel_from_arrays, panel_quality


def _rows(naive=False, tz_hour=23):
    return [obs("mood", 6.0, utc(2026, 10, 9, tz_hour, 30, naive=naive)), obs("mood", 8.0, utc(2026, 10, 9, 12, 0, naive=naive))]


def test_naive_datetimes_are_treated_as_utc_not_server_local():
    # 23:30 UTC is already the next calendar day in Lagos (UTC+1); a naive value must not be shifted by server time.
    p = build_panel(_rows(naive=True), tz="Africa/Lagos", end=utc(2026, 10, 10, 18), window_days=5)
    day = {d.isoformat(): v for d, v in zip(p.dates, p.variables["mood"])}
    assert day["2026-10-10"] == 6.0           # the 23:30 UTC entry -> 00:30 on the 10th in Lagos
    assert day["2026-10-09"] == 8.0
    aware = build_panel(_rows(naive=False), tz="Africa/Lagos", end=utc(2026, 10, 10, 18), window_days=5)
    assert np.array_equal(np.nan_to_num(aware.variables["mood"], nan=-1), np.nan_to_num(p.variables["mood"], nan=-1))


def test_missing_days_stay_nan_and_are_never_zero_imputed():
    rows = [obs("energy", 7.0, utc(2026, 10, 1)), obs("energy", 5.0, utc(2026, 10, 5))]
    p = build_panel(rows, tz="UTC", end=utc(2026, 10, 6), window_days=6)
    v = p.variables["energy"]
    assert int(np.isnan(v).sum()) == 4 and not (v == 0).any()


def test_multiple_entries_per_day_are_averaged_and_flagged():
    rows = [obs("stress", 4.0, utc(2026, 10, 2, 8)), obs("stress", 6.0, utc(2026, 10, 2, 20))]
    p = build_panel(rows, tz="UTC", end=utc(2026, 10, 3), window_days=3)
    assert p.variables["stress"][1] == 5.0 and p.multi_entry_days["stress"] == 1
    q = panel_quality(p)
    assert any("multiple_entries" in w for w in q["warnings"])


def test_unknown_timezone_falls_back_to_utc_and_says_so():
    p = build_panel([obs("mood", 5.0, utc(2026, 10, 2))], tz="Mars/Olympus", end=utc(2026, 10, 3), window_days=3)
    assert p.tz_fallback is True
    assert "timezone_unresolved_utc_day_boundaries_used" in panel_quality(p)["warnings"]


def test_poor_quality_and_deviation_biomarkers_are_excluded():
    bm = [
        SimpleNamespace(marker_code="CRP", value_numeric=3.0, recorded_at=utc(2026, 10, 2), quality="good", result_mode="quantitative"),
        SimpleNamespace(marker_code="LDL", value_numeric=9.0, recorded_at=utc(2026, 10, 2), quality="poor", result_mode="quantitative"),
        SimpleNamespace(marker_code="HBA1C", value_numeric=5.5, recorded_at=utc(2026, 10, 2), quality="good", result_mode="deviation"),
    ]
    p = build_panel([], tz="UTC", end=utc(2026, 10, 3), window_days=3, biomarkers=bm)
    assert list(p.variables) == ["bm:crp"] and p.sources["bm:crp"] == "biomarker"


def test_digest_is_stable_and_sensitive_to_data():
    a = panel_from_arrays({"x": [1.0, 2.0, np.nan, 4.0], "y": [2.0, 3.0, 4.0, 5.0]}, utc(2026, 1, 1).date())
    b = panel_from_arrays({"y": [2.0, 3.0, 4.0, 5.0], "x": [1.0, 2.0, np.nan, 4.0]}, utc(2026, 1, 1).date())
    c = panel_from_arrays({"x": [1.0, 2.0, np.nan, 4.1], "y": [2.0, 3.0, 4.0, 5.0]}, utc(2026, 1, 1).date())
    assert a.digest() == b.digest() and a.digest() != c.digest()


def test_quality_flags_straight_lined_and_scarce_variables():
    rng = np.random.default_rng(1)
    n = 60
    p = panel_from_arrays({
        "mood": rng.integers(3, 9, n).astype(float),
        "energy": np.full(n, 7.0),                                  # straight-lined
        "focus": np.where(np.arange(n) < 5, 6.0, np.nan),          # too few days
    }, utc(2026, 1, 1).date())
    q = panel_quality(p)
    assert q["eligible_variables"] == ["mood"]
    assert "near_constant_or_straight_lined" in q["ineligible_variables"]["energy"]
    assert "too_few_observed_days" in q["ineligible_variables"]["focus"]
    assert 0 <= q["score"] <= 100


def test_window_excludes_old_and_future_rows():
    rows = [obs("mood", 5.0, utc(2026, 9, 1)), obs("mood", 6.0, utc(2026, 10, 2)), obs("mood", 7.0, utc(2026, 11, 20))]
    p = build_panel(rows, tz="UTC", end=utc(2026, 10, 5), window_days=10)
    assert int((~np.isnan(p.variables["mood"])).sum()) == 1
