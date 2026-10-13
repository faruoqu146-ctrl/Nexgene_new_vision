import math

from _research_helpers import ROOT  # noqa: F401  (sets sys.path)
from backend.app.research import special as sp

# Reference values computed with SciPy 1.17 (stats.t.sf, stats.t.ppf, stats.f.sf, special.betainc).
T_TWO_SIDED = [
    (1.4142135623730951, 6, 0.20703125), (2.0, 10, 0.07338803477074037), (2.5, 30, 0.01811564906806669),
    (3.1, 59, 0.0029648557936072326), (0.0, 5, 1.0), (5.0, 4, 0.007490433881274525), (1.96, 1000, 0.050273184955748736),
]
T_PPF = [(0.975, 10, 2.228138851986274), (0.975, 30, 2.0422724563012378), (0.95, 5, 2.0150483733330233),
         (0.99, 59, 2.3912288372073567), (0.8, 13, 0.8701515339681739)]


def test_student_t_two_sided_p_matches_reference():
    for t, df, ref in T_TWO_SIDED:
        assert math.isclose(sp.t_two_sided_p(t, df), ref, rel_tol=1e-9, abs_tol=1e-12)


def test_student_t_quantiles_match_reference():
    for p, df, ref in T_PPF:
        assert math.isclose(sp.t_ppf(p, df), ref, rel_tol=1e-9)


def test_t_quantile_inverts_cdf():
    for df in (3, 9, 27, 81):
        for p in (0.01, 0.2, 0.5, 0.9, 0.995):
            assert abs(sp.t_cdf(sp.t_ppf(p, df), df) - p) < 1e-10


def test_normal_functions():
    assert math.isclose(sp.norm_ppf(0.975), 1.959963984540054, rel_tol=1e-12)
    assert math.isclose(sp.norm_ppf(0.8), 0.8416212335729143, rel_tol=1e-12)
    assert abs(sp.norm_cdf(sp.norm_ppf(0.123)) - 0.123) < 1e-12
    assert sp.norm_ppf(0.0) == -math.inf and sp.norm_ppf(1.0) == math.inf


def test_f_survival_and_incomplete_beta():
    assert math.isclose(sp.f_sf(3.0, 2, 20), 0.07253815028640571, rel_tol=1e-9)
    assert math.isclose(sp.f_sf(1.5, 5, 40), 0.21154656166470256, rel_tol=1e-9)
    assert math.isclose(sp.betainc(2.0, 3.0, 0.4), 0.5248, rel_tol=1e-12)
    assert math.isclose(sp.betainc(0.5, 0.5, 0.9), 0.7951672353008665, rel_tol=1e-9)


def test_degenerate_inputs_are_safe():
    assert sp.t_two_sided_p(float("nan"), 5) == 1.0
    assert sp.t_two_sided_p(float("inf"), 5) == 0.0
    assert sp.t_two_sided_p(2.0, 0) == 1.0
    assert sp.fisher_z(1.0) < 20 and sp.fisher_z(-1.0) > -20          # clipped, never infinite
