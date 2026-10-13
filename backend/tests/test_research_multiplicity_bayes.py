import math

import numpy as np

from _research_helpers import ROOT  # noqa: F401
from backend.app.research.bayes import bf_label, default_prior_summary, fit_two_group, posterior
from backend.app.research.multiplicity import bh_adjust, by_adjust, holm_adjust, storey_pi0

P = [0.01, 0.04, 0.03, 0.005]


def test_bh_matches_hand_computation_and_is_monotone():
    assert np.allclose(bh_adjust(P), [0.02, 0.04, 0.04, 0.02])
    p = np.sort(np.random.default_rng(1).random(40) ** 2)
    q = bh_adjust(p)
    assert (np.diff(q) >= -1e-15).all() and (q >= p - 1e-15).all() and q.max() <= 1.0


def test_holm_matches_hand_computation():
    assert np.allclose(holm_adjust(P), [0.03, 0.06, 0.06, 0.02])


def test_by_is_more_conservative_than_bh_and_capped():
    q_bh, q_by = bh_adjust(P), by_adjust(P)
    assert (q_by >= q_bh - 1e-15).all() and q_by.max() <= 1.0
    assert math.isclose(q_by[3], min(1.0, 0.02 * (1 + 1 / 2 + 1 / 3 + 1 / 4)))


def test_empty_and_single_families():
    assert len(bh_adjust([])) == 0 and bh_adjust([0.3])[0] == 0.3 and holm_adjust([0.3])[0] == 0.3


def test_storey_pi0_on_pure_nulls_is_near_one():
    assert storey_pi0(np.random.default_rng(3).random(500)) > 0.85
    assert storey_pi0([0.01, 0.2]) == 1.0                 # too few p-values to estimate


def test_empirical_bayes_corrects_the_winners_curse():
    rng = np.random.default_rng(1)
    m = 600
    se = np.full(m, 0.15)
    theta = np.where(rng.random(m) < 0.1, rng.normal(0, 0.35, m), 0.0)
    z = theta + rng.normal(0, 1, m) * se
    fit = fit_two_group(z, se)
    assert fit["fitted"] and 0.6 < fit["pi0"] < 0.97 and 0.1 < fit["tau"] < 0.6
    shrunk = np.array([posterior(zi, s, fit["pi0"], fit["tau"])["z_shrunk"] for zi, s in zip(z, se)])
    assert np.mean((shrunk - theta) ** 2) < 0.5 * np.mean((z - theta) ** 2)
    top = np.argsort(-np.abs(z))[:10]
    assert abs(np.abs(shrunk[top]).mean() - np.abs(theta[top]).mean()) < abs(np.abs(z[top]).mean() - np.abs(theta[top]).mean())


def test_eb_with_too_few_tests_declines_to_fit():
    assert fit_two_group([0.1, 0.2], [0.1, 0.1])["fitted"] is False


def test_posterior_probabilities_behave():
    strong = posterior(0.9, 0.12, 0.8, 0.3)
    weak = posterior(0.05, 0.12, 0.8, 0.3)
    assert strong["p_non_null"] > 0.95 > 0.5 > weak["p_non_null"]
    assert 0 < strong["z_shrunk"] < 0.9 and weak["z_shrunk"] < 0.1


def test_default_prior_bayes_factor_and_labels():
    lo = default_prior_summary(0.1, 0.15, 0.3, 0.1)
    hi = default_prior_summary(0.6, 0.15, 0.3, 0.1)
    assert hi["log10_bf10"] > lo["log10_bf10"] and lo["log10_bf10"] < 0          # small z favours the null
    assert 0.5 <= hi["p_direction"] <= 1 and hi["p_practical"] > lo["p_practical"]
    assert bf_label(0.1) == "anecdotal" and "no effect" in bf_label(-1.2) and "decisive" in bf_label(2.5)
