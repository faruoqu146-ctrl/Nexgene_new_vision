import math

import numpy as np

from _research_helpers import null_panel, planted_panel
from backend.app.research import inference as inf
from backend.app.research.config import DEFAULT_CONFIG as CFG


def _prepared(panel, names):
    D = inf.build_design(panel.ordinals, panel.weekdays)
    return D, {n: inf.prepare_variable(n, panel.variables[n], D, CFG) for n in names}


def test_residualisation_removes_weekday_and_trend_but_keeps_gaps():
    T = 84
    wd = np.arange(T) % 7
    y = 5 + 2.0 * (wd == 5) - 1.5 * (wd == 2) + 0.03 * np.arange(T) + np.random.default_rng(0).normal(0, 0.1, T)
    y[[10, 11, 40]] = np.nan
    panel_dates = np.array([738000 + i for i in range(T)])
    D = inf.build_design(panel_dates, (np.arange(T) % 7))
    r = inf.residualize(y, D)
    assert np.isnan(r[[10, 11, 40]]).all()
    ok = ~np.isnan(r)
    assert np.std(r[ok]) < 0.2                       # structure removed, only the 0.1 noise remains
    assert abs(np.mean(r[ok])) < 1e-9


def test_calendar_lag_never_crosses_a_missing_day():
    rx = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0])
    ry = np.array([1.0, np.nan, 3.0, 4.0, 5.0, 6.0])
    a, b, idx = inf.pair_arrays(rx, ry, 1)
    # pairs are (x[t], y[t+1]): t=0 -> y[1] is missing (dropped); t=2 -> x[2] is missing (dropped);
    # surviving pairs are strictly (t, t+1): (x1,y2), (x3,y4), (x4,y5) and nothing is bridged across a gap.
    assert idx.tolist() == [1, 3, 4] and a.tolist() == [2.0, 4.0, 5.0] and b.tolist() == [3.0, 5.0, 6.0]
    a0, b0, idx0 = inf.pair_arrays(rx, ry, 0)
    assert idx0.tolist() == [0, 3, 4, 5]


def test_rank_average_handles_ties():
    assert inf.rank_avg(np.array([1.0, 2.0, 2.0, 3.0])).tolist() == [1.0, 2.5, 2.5, 4.0]


def test_null_kernel_stays_away_from_every_hypothesised_lag():
    k = inf.NullKernel(T=60, max_lag=2, buffer=3)
    assert k.ks.min() == 6 and k.ks.max() == 56 and k.n_shifts == 51
    assert k.idx.shape == (51, 60)


def test_planted_lagged_effect_is_detected_with_correct_sign_and_conservative_p():
    p = planted_panel(seed=11, T=90, effects=[("activity_duration", "mood", 1, 1.4)])
    D, prep = _prepared(p, ["activity_duration", "mood"])
    kern = inf.NullKernel(p.T, 2, CFG.shift_buffer)
    s = inf.screen_pair(prep["activity_duration"], prep["mood"], 1, kern, CFG)
    assert s is not None and s.r_adj > 0.5 and s.p_combined < 1e-4
    parts = [x for x in (s.p_hac, s.p_eff, s.p_shift_gauss) if x is not None]
    assert s.p_combined == max(parts)                    # the reported p is the most conservative valid test
    lo, hi = s.r_ci(0.95)
    assert lo < s.r_adj < hi and lo > 0


def test_independent_autocorrelated_pairs_are_rarely_declared_significant():
    kern = inf.NullKernel(90, 2, CFG.shift_buffer)
    hits = n = 0
    for seed in range(60):
        p = null_panel(seed=100 + seed, T=90, names=["caffeine", "mood"])
        D, prep = _prepared(p, ["caffeine", "mood"])
        s = inf.screen_pair(prep["caffeine"], prep["mood"], 0, kern, CFG)
        if s is not None:
            n += 1
            hits += s.p_combined <= 0.05
    assert n >= 50 and hits / n <= 0.15               # nominal 5%; generous bound keeps the test stable across RNG versions


def test_naive_pearson_is_much_looser_than_the_calibrated_test_on_autocorrelated_data():
    rng = np.random.default_rng(5)
    kern = inf.NullKernel(90, 2, CFG.shift_buffer)
    naive_hits = cal_hits = n = 0
    for _ in range(80):
        p = null_panel(seed=int(rng.integers(1, 10 ** 6)), T=90, names=["caffeine", "mood"], missing=0.05)
        D, prep = _prepared(p, ["caffeine", "mood"])
        s = inf.screen_pair(prep["caffeine"], prep["mood"], 0, kern, CFG)
        a, b, _ = inf.pair_arrays(prep["caffeine"].raw, prep["mood"].raw, 0)
        r = np.corrcoef(a, b)[0, 1]
        from backend.app.research.special import t_two_sided_p
        pn = t_two_sided_p(r * math.sqrt((len(a) - 2) / (1 - r * r)), len(a) - 2)
        n += 1
        naive_hits += pn <= 0.05
        cal_hits += s.p_combined <= 0.05
    assert naive_hits > cal_hits                       # calibration removes false positives that naive tests make


def _ols_se(x, y):
    xc = x - x.mean()
    beta = float(xc @ (y - y.mean())) / float(xc @ xc)
    resid = (y - y.mean()) - beta * xc
    return beta, math.sqrt(float(resid @ resid) / (len(x) - 2) / float(xc @ xc))


def test_hac_standard_error_is_close_to_ols_for_independent_data():
    rng = np.random.default_rng(2)
    n = 400
    x = rng.normal(size=n)
    y = 0.4 * x + rng.normal(size=n)
    h = inf.hac_slope_test(x, y, 0)
    beta, ols_se = _ols_se(x, y)
    assert abs(h.beta - beta) < 1e-9 and 0.7 < h.se / ols_se < 1.4 and h.bandwidth >= 2


def test_hac_inflates_the_standard_error_under_persistent_noise():
    ratios = []
    for seed in range(10):
        rng = np.random.default_rng(seed)
        n = 400
        def ar(phi):
            z = np.zeros(n)
            for t in range(1, n):
                z[t] = phi * z[t - 1] + rng.normal()
            return z
        xs, e = ar(0.8), ar(0.8)
        h = inf.hac_slope_test(xs, e, 0)
        ratios.append(h.se / _ols_se(xs, e)[1])
    # HAC corrects only part of the dependence (hence the engine also uses the shift null and Bartlett effective-N)
    assert np.mean(ratios) > 1.3


def test_effective_shifts_shrinks_for_persistent_nulls():
    rng = np.random.default_rng(4)
    iid = rng.normal(size=80)
    walk = np.cumsum(rng.normal(size=80))
    assert inf.effective_shifts(iid) > 40 and inf.effective_shifts(walk) < 15


def test_e_value_reference_and_null_interval():
    d = math.log(2.0) / 0.91                           # RR = 2  ->  E = 2 + sqrt(2)
    ev = inf.e_value(d, (d * 0.5, d * 1.5))
    assert math.isclose(ev["e_value"], 2 + math.sqrt(2), rel_tol=1e-9)
    assert ev["e_value_ci"] > 1.0
    assert inf.e_value(0.3, (-0.1, 0.5))["e_value_ci"] == 1.0   # CI includes the null -> nothing to explain away
    assert inf.e_value(-d)["e_value"] == ev["e_value"]          # symmetric in sign


def test_power_functions_match_closed_forms():
    r = inf.minimum_detectable_r(100.0, 0.05, 0.80)
    assert math.isclose(r, math.tanh((1.959963984540054 + 0.8416212335729143) / math.sqrt(97)), rel_tol=1e-9)
    assert inf.days_needed(0.3, 1.0) == 85
    assert inf.days_needed(0.3, 0.5) > 2 * 84             # fewer effective days per calendar day -> more calendar days
    assert inf.minimum_detectable_r(3.0) is None and inf.days_needed(0.0, 1.0) is None


def test_block_bootstrap_interval_is_seeded_and_brackets_the_estimate():
    rng = np.random.default_rng(8)
    a = rng.normal(size=70)
    b = 0.6 * a + rng.normal(size=70) * 0.8
    r1 = inf.block_bootstrap_ci(a, b, np.random.default_rng(1), 500, 0.9)
    r2 = inf.block_bootstrap_ci(a, b, np.random.default_rng(1), 500, 0.9)
    assert r1 == r2 and r1[0] < np.corrcoef(a, b)[0, 1] < r1[1]


def test_direction_verdict_uses_a_stricter_forward_threshold_than_the_reverse_block():
    from backend.app.research.config import DEFAULT_CONFIG
    f = lambda p, r: {"evaluable": True, "p": p, "r_partial": r}
    v = inf.direction_verdict
    assert v(f(0.03, 0.4), f(0.5, 0.1), DEFAULT_CONFIG)["direction_supported"] is False        # 0.03 > directional_alpha 0.01
    assert v(f(0.004, 0.4), f(0.5, 0.1), DEFAULT_CONFIG)["direction_supported"] is True
    assert v(f(0.004, 0.4), f(0.03, 0.38), DEFAULT_CONFIG)["direction_supported"] is False     # reverse also significant, not weaker
    assert v(f(0.004, 0.5), f(0.03, 0.2), DEFAULT_CONFIG)["direction_supported"] is True       # reverse significant but clearly weaker
    assert v({"evaluable": False}, f(0.001, 0.5), DEFAULT_CONFIG) == {}
