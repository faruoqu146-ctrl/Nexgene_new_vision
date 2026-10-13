import copy

from _research_helpers import ROOT  # noqa: F401
from backend.app.research.config import DEFAULT_CONFIG as CFG
from backend.app.research.gates import evaluate_gates


def cand(**o):
    c = {
        "id": "caffeine->sleep_quality@1", "exposure": "caffeine", "outcome": "sleep_quality", "lag": 1, "n_pairs": 60, "active_weeks": 9,
        "missingness": {"pair_missingness_rate": 0.1},
        "effect": {"r_adj": -0.45},
        "inference": {"p_combined": 0.001, "q_family_bh": 0.01},
        "robustness": {"robust": True, "sign_consistent": True, "outlier_stable": True, "bootstrap_excludes_zero": True},
        "directional_test": {"evaluable": True, "forward": {"r_partial": -0.40, "p": 0.004}, "reverse_significant": False, "direction_supported": True},
    }
    for k, v in o.items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            c[k] = {**c[k], **v}
        else:
            c[k] = v
    return c


def level(c, **kw):
    return evaluate_gates(c, CFG, **kw)


def test_strong_lagged_candidate_reaches_erl3_and_every_gate_is_listed():
    v = level(cand())
    assert v["tier"]["level"] == 3 and v["status"] == "SUPPORTED"
    ids = [g["id"] for g in v["gates"]]
    assert ids == ["data_sufficiency", "false_discovery_control", "practical_effect_size", "robustness", "prior_concordance",
                   "temporal_order", "prospective_validation", "randomised_experiment"]
    assert all("detail" in g and g["detail"] for g in v["gates"])


def test_same_day_pair_is_capped_at_erl2_because_direction_is_unidentifiable():
    v = level(cand(lag=0, directional_test=None))
    assert v["tier"]["level"] == 2
    assert next(g for g in v["gates"] if g["id"] == "temporal_order")["passed"] is None


def test_thin_data_is_insufficient_not_supported():
    v = level(cand(n_pairs=9))
    assert v["tier"]["level"] == 0 and v["tier"]["reason"] == "insufficient_data" and v["status"] == "INCONCLUSIVE"
    v2 = level(cand(n_pairs=18))                 # enough to test, not enough to claim
    assert v2["tier"]["level"] == 1 and v2["status"] == "TESTING"
    v3 = level(cand(active_weeks=2))
    assert v3["tier"]["level"] == 1


def test_fdr_effect_floor_and_robustness_each_block_erl2():
    assert level(cand(inference={"q_family_bh": 0.2}))["tier"]["level"] == 1
    assert level(cand(effect={"r_adj": -0.12}))["tier"]["level"] == 1
    c = cand()
    c["robustness"] = {**c["robustness"], "robust": False}
    assert level(c)["tier"]["level"] == 1
    c2 = cand()
    c2["robustness"] = None
    assert level(c2)["tier"]["level"] == 1


def test_no_detectable_signal_is_reported_as_such():
    v = level(cand(inference={"p_combined": 0.6, "q_family_bh": 0.9}, effect={"r_adj": 0.05}))
    assert v["tier"]["level"] == 0 and v["tier"]["reason"] == "no_detectable_signal"


def test_reviewed_prior_that_disagrees_blocks_but_unreviewed_or_uncited_priors_are_ignored():
    bad = {"expected_sign": 1, "review_status": "reviewed", "citations": ["doi:x"]}
    assert level(cand(), prior=bad)["tier"]["level"] == 1
    ok = {"expected_sign": -1, "review_status": "reviewed", "citations": ["doi:x"]}
    assert level(cand(), prior=ok)["tier"]["level"] == 3
    assert level(cand(), prior={"expected_sign": 1, "review_status": "unreviewed", "citations": ["doi:x"]})["tier"]["level"] == 3
    assert level(cand(), prior={"expected_sign": 1, "review_status": "reviewed", "citations": []})["tier"]["level"] == 3


def test_directional_failure_keeps_candidate_at_erl2():
    dt = {"evaluable": True, "forward": {"r_partial": -0.4, "p": 0.004}, "reverse_significant": True, "direction_supported": False}
    assert level(cand(directional_test=dt))["tier"]["level"] == 2


def test_prospective_confirmation_promotes_and_failure_weakens():
    good = {"scored_days": 40, "informative_days": 14, "evidence_ratio": 35.0, "hits": 11, "misses": 3}
    v = level(cand(), track=good)
    assert v["tier"]["level"] == 4 and v["status"] == "CONFIRMED"
    thin = {**good, "informative_days": 6}
    assert level(cand(), track=thin)["tier"]["level"] == 3                 # not enough informative days yet
    bad = {"scored_days": 30, "informative_days": 12, "evidence_ratio": 0.05, "hits": 3, "misses": 9}
    w = level(cand(), track=bad)
    assert w["status"] == "WEAKENED" and w["tier"]["level"] <= 2 and w["notes"]


def test_randomised_experiment_is_the_only_route_to_erl5_and_can_falsify():
    sup = level(cand(), experiment={"verdict": "SUPPORTED"})
    assert sup["tier"]["level"] == 5 and sup["status"] == "CONFIRMED"
    for verdict in ("REFUTED", "CONTRADICTED"):
        f = level(cand(), experiment={"verdict": verdict})
        assert f["status"] == "FALSIFIED" and f["tier"]["level"] <= 1
    assert level(cand(), experiment={"verdict": "INCONCLUSIVE"})["tier"]["level"] == 3


def test_gates_do_not_mutate_their_input():
    c = cand()
    snap = copy.deepcopy(c)
    level(c, track={"scored_days": 5, "informative_days": 1, "evidence_ratio": 1.0})
    assert c == snap
