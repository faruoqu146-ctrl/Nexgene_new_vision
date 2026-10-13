"""Statistical guard-rails carried over from Phase 11 and extended for the Phase 12 engine."""
import numpy as np

from _research_helpers import ROOT  # noqa: F401
from backend.app.research import inference as inf
from backend.app.research.config import DEFAULT_CONFIG as CFG, EngineConfig
from backend.app.research.discovery import _missingness
from backend.app.research.panel import panel_from_arrays


def test_shift_calibrated_test_detects_a_planted_daily_alignment():
    rng = np.random.default_rng(451)
    x = rng.normal(size=60)
    y = 0.9 * x + rng.normal(0, 0.25, 60)
    p = panel_from_arrays({"caffeine": x, "mood": y}, __import__("datetime").date(2026, 1, 1))
    D = inf.build_design(p.ordinals, p.weekdays)
    px, py = (inf.prepare_variable(n, p.variables[n], D, CFG) for n in ("caffeine", "mood"))
    s = inf.screen_pair(px, py, 0, inf.NullKernel(60, 2, CFG.shift_buffer), CFG)
    assert s.p_shift_gauss is not None and 0 < s.p_shift_gauss <= 0.10
    assert s.p_shift_rank is not None and s.p_shift_rank <= 0.10


def test_empirical_null_is_declined_when_the_series_is_too_short_to_shift():
    rng = np.random.default_rng(1)
    x, y = rng.normal(size=22), rng.normal(size=22)
    p = panel_from_arrays({"caffeine": x, "mood": y}, __import__("datetime").date(2026, 1, 1))
    D = inf.build_design(p.ordinals, p.weekdays)
    px, py = (inf.prepare_variable(n, p.variables[n], D, CFG) for n in ("caffeine", "mood"))
    s = inf.screen_pair(px, py, 0, inf.NullKernel(22, 2, CFG.shift_buffer), EngineConfig(min_pairs=14, min_shifts=20))
    assert s is not None and s.p_shift_gauss is None and "shift-calibrated" not in s.p_method


def test_too_few_overlapping_days_are_not_tested_at_all():
    p = panel_from_arrays({"caffeine": np.r_[np.arange(10.0), [np.nan] * 40], "mood": np.r_[[np.nan] * 40, np.arange(10.0)]}, __import__("datetime").date(2026, 1, 1))
    D = inf.build_design(p.ordinals, p.weekdays)
    px, py = (inf.prepare_variable(n, p.variables[n], D, CFG) for n in ("caffeine", "mood"))
    assert inf.screen_pair(px, py, 0, inf.NullKernel(50, 2, CFG.shift_buffer), CFG) is None


def test_missingness_reports_gaps_without_zero_imputation():
    mx = np.array([True, True, False, True])        # sleep observed days 1,2,4
    my = np.array([True, False, True, True])        # focus observed days 1,3,4
    r = _missingness(mx, my, 0, np.array([0, 3]))
    assert r["expected_pair_days"] == 4 and r["observed_pair_days"] == 2 and r["missing_pair_days"] == 2
    assert r["pair_missingness_rate"] == 0.5 and r["zero_imputation_used"] is False and r["longest_pair_gap_days"] == 2


def test_missingness_for_unobserved_variables_is_explicitly_unknown():
    r = _missingness(np.zeros(5, dtype=bool), np.zeros(5, dtype=bool), 0, np.array([], dtype=int))
    assert r["expected_pair_days"] == 0 and r["pair_missingness_rate"] is None


def test_leading_and_trailing_absence_is_not_counted_as_missingness():
    mx = np.array([False, False, True, True, True, True, False, False])
    my = mx.copy()
    r = _missingness(mx, my, 0, np.array([2, 3, 4, 5]))
    assert r["expected_pair_days"] == 4 and r["pair_missingness_rate"] == 0.0


def test_adjusting_for_a_shared_weekly_cycle_removes_a_spurious_association():
    T = 98
    wd = np.arange(T) % 7
    rng = np.random.default_rng(3)
    x = 3.0 * (wd >= 5) + rng.normal(0, 0.5, T)           # both variables simply rise on weekends
    y = 2.0 * (wd >= 5) + rng.normal(0, 0.5, T)
    p = panel_from_arrays({"caffeine": x, "mood": y}, __import__("datetime").date(2026, 1, 5))
    D = inf.build_design(p.ordinals, p.weekdays)
    px, py = (inf.prepare_variable(n, p.variables[n], D, CFG) for n in ("caffeine", "mood"))
    s = inf.screen_pair(px, py, 0, inf.NullKernel(T, 2, CFG.shift_buffer), CFG)
    assert abs(s.r_raw) > 0.6 and abs(s.r_adj) < 0.3 and s.p_combined > 0.01


def test_a_shared_linear_trend_is_not_mistaken_for_a_relationship():
    T = 90
    rng = np.random.default_rng(4)
    t = np.arange(T)
    x = 0.05 * t + rng.normal(0, 0.5, T)
    y = 0.04 * t + rng.normal(0, 0.5, T)
    p = panel_from_arrays({"caffeine": x, "mood": y}, __import__("datetime").date(2026, 1, 5))
    D = inf.build_design(p.ordinals, p.weekdays)
    px, py = (inf.prepare_variable(n, p.variables[n], D, CFG) for n in ("caffeine", "mood"))
    s = inf.screen_pair(px, py, 0, inf.NullKernel(T, 2, CFG.shift_buffer), CFG)
    assert abs(s.r_raw) > 0.6 and abs(s.r_adj) < 0.3
