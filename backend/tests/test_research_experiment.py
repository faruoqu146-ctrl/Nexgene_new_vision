import math
from datetime import date, timedelta

import numpy as np

from _research_helpers import ROOT  # noqa: F401
from backend.app.research.experiment import (
    analyze_experiment, design_experiment, design_power, expected_direction_from_observation, randomisation_ci,
    signflip_p, verify_preregistration,
)
from backend.app.research.panel import panel_from_arrays

START = date(2026, 3, 2)


def _design(seed=123, **kw):
    args = dict(exposure="caffeine", outcome="sleep_quality", start=START, seed=seed, lag=0, n_blocks=14, period_len=1,
                intervention="decrease", expected_direction="higher", hypothesis_id="h1")
    args.update(kw)
    return design_experiment(**args)


def test_schedule_is_reproducible_balanced_and_tamper_evident():
    a, b = _design()["preregistration"], _design()["preregistration"]
    assert a["hash"] == b["hash"] and verify_preregistration(a)
    for blk in range(14):
        conds = [s["condition"] for s in a["schedule"] if s["block"] == blk]
        assert sorted(conds) == ["A", "B"]                        # one of each within every block
    assert a["schedule"][0]["date"] == START.isoformat() and a["end"] == (START + timedelta(days=27)).isoformat()
    assert _design(seed=124)["preregistration"]["hash"] != a["hash"]
    tampered = {**a, "n_blocks": 15}
    assert not verify_preregistration(tampered)
    swapped = {**a, "schedule": [{**s, "condition": "B" if s["condition"] == "A" else "A"} for s in a["schedule"]]}
    assert not verify_preregistration(swapped)


def test_order_within_blocks_is_randomised_roughly_evenly():
    firsts = [next(s for s in _design(seed=sd, n_blocks=40)["preregistration"]["schedule"] if s["block"] == 0)["condition"] for sd in range(200)]
    assert 70 < firsts.count("B") < 130


def test_design_validation():
    for bad in (dict(n_blocks=3), dict(period_len=9), dict(washout_days=1, period_len=1), dict(lag=7), dict(intervention="swap"),
                dict(exposure="mood", outcome="mood")):
        try:
            _design(**bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid design {bad}")


def test_washout_days_are_excluded_from_the_analysis_set():
    d = _design(period_len=3, washout_days=1, n_blocks=8)["preregistration"]
    flags = [s["analysis_day"] for s in d["schedule"]]
    assert flags.count(False) == 8 * 2 and len(flags) == 48


def test_exact_sign_flip_p_value_reference():
    assert math.isclose(signflip_p(np.ones(6), 1)[0], 2 / 64)          # only all-same-sign assignments are as extreme
    assert signflip_p(np.array([1.0, -1.0, 1.0, -1.0]), 1)[0] == 1.0
    p, exact = signflip_p(np.ones(20), 5)
    assert not exact and p < 1e-3                                        # Monte Carlo branch above 16 blocks


def test_randomisation_interval_contains_the_estimate_and_excludes_zero_for_a_clear_effect():
    d = np.array([1.2, 0.8, 1.5, 0.9, 1.1, 1.4, 0.7, 1.0])
    lo, hi, bounded = randomisation_ci(d, 3)
    assert bounded and lo < d.mean() < hi and lo > 0


def _simulate(rng, effect, compliance=0.9, seed=None, lag=0, ar=0.4, n_blocks=14, sd=1.5):
    seed = int(rng.integers(1, 10 ** 9)) if seed is None else seed
    pre = _design(seed=seed, lag=lag, n_blocks=n_blocks)["preregistration"]
    sched = pre["schedule"]
    T = len(sched) + lag + 4
    e = np.zeros(T)
    for t in range(1, T):
        e[t] = ar * e[t - 1] + math.sqrt(1 - ar ** 2) * rng.standard_normal()
    y, x = 6 + sd * e, 3.0 + rng.normal(0, 0.3, T)
    for k, s in enumerate(sched):
        if s["condition"] == "B" and rng.random() < compliance:
            x[k] = 1.0 + rng.normal(0, 0.3)
            y[k + lag] += effect
    return pre, panel_from_arrays({"caffeine": x, "sleep_quality": y}, START), START + timedelta(days=T + 2)


def test_interim_analysis_withholds_effect_estimates():
    rng = np.random.default_rng(1)
    pre, panel, _ = _simulate(rng, 2.0)
    r = analyze_experiment(pre, panel, START + timedelta(days=9))
    assert r["status"] == "IN_PROGRESS" and r["estimates_withheld"] is True and "itt" not in r and "verdict" not in r
    assert r["exposure_logged_days"]["A"] + r["exposure_logged_days"]["B"] > 0       # adherence progress is shown


def test_strong_effect_is_supported_with_a_passing_manipulation_check():
    rng = np.random.default_rng(2)
    pre, panel, today = _simulate(rng, 3.0, seed=77)
    r = analyze_experiment(pre, panel, today)
    assert r["status"] == "COMPLETE_SCHEDULE" and r["manipulation_check"]["passed"] is True
    assert r["verdict"] == "SUPPORTED" and r["itt"]["p_randomisation"] < 0.01 and r["itt"]["ci95"][0] > 0
    assert r["bayes"]["p_effect_positive"] > 0.95 and r["complier_effect"] is not None


def test_randomisation_test_has_correct_size_under_no_effect():
    rng = np.random.default_rng(3)
    rejections = n = 0
    for _ in range(120):
        pre, panel, today = _simulate(rng, 0.0)
        r = analyze_experiment(pre, panel, today)
        if "itt" in r:
            n += 1
            rejections += r["itt"]["p_randomisation"] <= 0.05
    assert n >= 110 and rejections / n <= 0.12          # nominal <= 5%, exact test; generous bound for sampling noise


def test_failed_manipulation_check_makes_the_result_uninterpretable():
    rng = np.random.default_rng(4)
    pre, panel, today = _simulate(rng, 3.0, compliance=0.0, seed=78)
    r = analyze_experiment(pre, panel, today)
    assert r["manipulation_check"]["passed"] is False and r["verdict"] == "INCONCLUSIVE"
    assert "manipulation check" in r["verdict_reason"]


def test_opposite_direction_effect_is_contradicted_not_supported():
    rng = np.random.default_rng(5)
    pre, panel, today = _simulate(rng, -3.0, seed=79)          # intervention LOWERS the outcome; pre-registered direction says higher
    r = analyze_experiment(pre, panel, today)
    assert r["verdict"] == "CONTRADICTED"


def test_tampered_preregistration_is_refused():
    rng = np.random.default_rng(6)
    pre, panel, today = _simulate(rng, 3.0, seed=80)
    forged = {**pre, "expected_direction": "lower"}
    assert analyze_experiment(forged, panel, today)["status"] == "INVALID"


def test_too_few_valid_blocks_is_inconclusive():
    rng = np.random.default_rng(7)
    pre, panel, today = _simulate(rng, 3.0, seed=81)
    sparse = {k: v.copy() for k, v in panel.variables.items()}
    sparse["sleep_quality"][8:] = np.nan                   # outcome logged for only the first few blocks
    p2 = panel_from_arrays(sparse, START)
    r = analyze_experiment(pre, p2, today)
    assert r["verdict"] == "INCONCLUSIVE" and "blocks" in r["reason"]


def test_power_calculation_is_monotone_and_honest_about_infeasible_designs():
    small = design_power(outcome_sd=1.5, rho=0.4, n_blocks=14, period_len=1)
    big = design_power(outcome_sd=1.5, rho=0.4, n_blocks=40, period_len=1)
    assert big["mde_80"] < small["mde_80"]
    need = design_power(outcome_sd=1.5, rho=0.4, n_blocks=14, period_len=1, effect=0.3)
    assert need["blocks_needed_for_effect"] is None or need["blocks_needed_for_effect"] > 60
    assert design_power(outcome_sd=None, rho=None, n_blocks=14, period_len=1)["available"] is False
    assert expected_direction_from_observation(-1, "decrease") == "higher" and expected_direction_from_observation(1, "decrease") == "lower"
    assert expected_direction_from_observation(1, "increase") == "higher"
