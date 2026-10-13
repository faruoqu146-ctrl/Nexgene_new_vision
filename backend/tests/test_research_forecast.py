import math
from datetime import timedelta

import numpy as np

from _research_helpers import planted_panel
from backend.app.research import analyze_panel
from backend.app.research.config import DEFAULT_CONFIG as CFG
from backend.app.research.forecast import (
    freeze_model, hit_rate_posterior, horizon_verdict, preregistration, score_frozen, summarize_track,
    verify_preregistration,
)

NAMES = ["caffeine", "alcohol", "mood", "energy", "sleep_quality"]


def _split(seed, beta, T=130, train=80):
    effects = [("caffeine", "sleep_quality", 1, beta)] if beta else []
    p = planted_panel(seed=seed, T=T, effects=effects, names=NAMES)
    return p, p.slice(0, train), train


def _frozen(seed, beta, pick=None):
    p, tr, train = _split(seed, beta)
    res = analyze_panel(tr, CFG)
    cand = next(c for c in res.candidates if c["id"] == pick) if pick else min(res.candidates, key=lambda c: c["inference"]["p_combined"])
    return p, tr, train, cand, freeze_model(tr, cand, CFG)


def test_locked_model_of_a_real_effect_beats_the_no_effect_model_on_unseen_days():
    ers = []
    for seed in range(21, 27):
        p, tr, train, cand, m = _frozen(seed, 1.2, "caffeine->sleep_quality@1")
        assert m is not None and m["sign"] == 1 and 0 < m["beta"] <= m["beta_unshrunk"] + 1e-12      # planted effect is positive; frozen effect is shrunk toward zero
        sc = score_frozen(m, p, p.dates[train], p.dates[-1], CFG)
        assert sc["scored_days"] >= 25 and sc["skill"] is not None
        ers.append(sc["evidence_ratio"])
    assert np.median(ers) > 5 and sum(e > 1 for e in ers) >= 5


def test_data_selected_spurious_candidates_are_almost_never_confirmed():
    confirmed = 0
    n = 0
    for seed in range(300, 324):
        p, tr, train, cand, m = _frozen(seed, 0.0)
        if m is None:
            continue
        sc = score_frozen(m, p, p.dates[train], p.dates[-1], CFG)
        n += 1
        confirmed += sc["evidence_ratio"] >= CFG.evidence_ratio_confirm
    assert n >= 20 and confirmed <= 1                  # Ville bound: P(ER >= 20 ever) <= 5% under no effect


def test_scoring_only_touches_days_after_the_freeze():
    p, tr, train, cand, m = _frozen(31, 1.2, "caffeine->sleep_quality@1")
    frozen_through = tr.dates[-1]
    sc = score_frozen(m, p, frozen_through + timedelta(days=1), p.dates[-1], CFG, keep_days=100)
    assert sc["scored_days"] > 0 and all(d["date"] > frozen_through.isoformat() for d in sc["days"])
    assert score_frozen(m, p, p.dates[-1] + timedelta(days=1), p.dates[-1] + timedelta(days=9), CFG)["scored_days"] == 0


def test_preregistration_is_tamper_evident():
    _, _, _, _, m = _frozen(31, 1.2, "caffeine->sleep_quality@1")
    pre = preregistration(m, "2026-10-11T00:00:00+00:00", 14)
    assert verify_preregistration(pre)
    forged = {**pre, "model": {**pre["model"], "beta": pre["model"]["beta"] * 3}}
    assert not verify_preregistration(forged)
    assert verify_preregistration({**pre, "issued_at": "2030-01-01T00:00:00+00:00"})   # issue time is metadata, not content


def test_freeze_declines_when_there_is_not_enough_history():
    p, tr, train = _split(31, 1.2)
    res = analyze_panel(tr, CFG)
    cand = next(c for c in res.candidates if c["id"] == "caffeine->sleep_quality@1")
    assert freeze_model(tr.slice(0, 12), cand, CFG) is None


def test_hit_rate_posterior_reference_values():
    a = hit_rate_posterior(3, 0)
    assert a["alpha"] == 4 and a["beta"] == 1 and math.isclose(a["p_gt_half"], 1 - 0.5 ** 4)
    b = hit_rate_posterior(0, 2)
    assert math.isclose(b["p_gt_half"], 0.5 ** 3) and math.isclose(b["mean"], 0.25)


def test_horizon_verdict_thresholds():
    ok = {"scored_days": 10, "evidence_ratio": 4.0}
    assert horizon_verdict(ok) == "SUPPORTED"
    assert horizon_verdict({**ok, "evidence_ratio": 0.2}) == "WEAKENED"
    assert horizon_verdict({**ok, "evidence_ratio": 1.0}) == "INCONCLUSIVE"
    assert horizon_verdict({"scored_days": 3, "evidence_ratio": 100.0}) == "INCONCLUSIVE"


def test_track_record_accumulates_log_evidence_across_forecasts():
    scores = [
        {"scored_days": 10, "informative_days": 5, "hits": 4, "misses": 1, "llr_sum": 1.0},
        {"scored_days": 12, "informative_days": 6, "hits": 5, "misses": 1, "llr_sum": 1.5},
        {"scored_days": 0, "informative_days": 0, "hits": 0, "misses": 0, "llr_sum": 0.0},
    ]
    t = summarize_track(scores, CFG)
    assert t["forecasts_completed"] == 2 and t["scored_days"] == 22 and t["hits"] == 9 and t["misses"] == 2
    assert math.isclose(t["evidence_ratio"], math.exp(2.5)) and t["interpretation"] == "accumulating"      # 12.2 < 20: not yet confirmed
    assert summarize_track([{"scored_days": 20, "informative_days": 10, "hits": 9, "misses": 1, "llr_sum": 4.0}], CFG)["interpretation"] == "confirmed"
