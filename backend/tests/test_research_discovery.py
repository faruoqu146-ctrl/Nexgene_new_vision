import json

import numpy as np

from _research_helpers import null_panel, planted_panel
from backend.app.research import analyze_panel
from backend.app.research.config import DEFAULT_CONFIG as CFG, EngineConfig
from backend.app.research.panel import panel_from_arrays
from backend.app.research.provenance import to_jsonable


def _ids(res, min_tier=2):
    return {c["id"] for c in res.candidates if c["tier"]["level"] >= min_tier}


def test_planted_effects_are_recovered_and_labelled_by_what_they_can_support():
    res = analyze_panel(planted_panel(seed=7))
    by_id = {c["id"]: c for c in res.candidates}
    lagged = by_id["activity_duration->mood@1"]
    same_day = by_id["focus->stress@0"] if "focus->stress@0" in by_id else by_id["stress->focus@0"]
    assert lagged["tier"]["level"] >= 3 and lagged["effect"]["r_adj"] > 0.4         # temporal order established
    assert same_day["tier"]["level"] == 2 and same_day["effect"]["r_adj"] < -0.4    # same-day: direction unidentifiable
    assert same_day["is_directional"] is False and lagged["is_directional"] is True
    assert lagged["status"] == "SUPPORTED"


def test_pure_noise_rarely_produces_robust_claims():
    # FDR control under a complete null means P(any false ERL>=2 claim) is about 5% per panel. Validation over 600
    # panels measured 4.2%; 36 fixed-seed panels with a loose bound keep this test stable across RNG versions.
    false_panels = sum(bool(_ids(analyze_panel(null_panel(seed=500 + i)), 2)) for i in range(36))
    assert false_panels <= 8, false_panels


def test_whole_family_is_tested_with_no_effect_size_prefilter():
    k = 5
    names = ["caffeine", "alcohol", "mood", "energy", "stress"]
    res = analyze_panel(null_panel(seed=9, missing=0.0, names=names))
    # same-day pairs are undirected (C(5,2)=10); lags 1 and 2 are directed (5*4*2=40)
    assert len(res.candidates) == 10 + 5 * 4 * 2
    assert sum(1 for c in res.candidates if c["lag"] == 0) == 10
    ids = [c["id"] for c in res.candidates]
    assert len(ids) == len(set(ids))
    weak = [c for c in res.candidates if abs(c["effect"]["r_adj"]) < 0.30]
    assert weak, "candidates with weak correlations must still be in the tested family"


def test_families_are_prespecified_from_the_taxonomy_not_from_the_data():
    res = analyze_panel(planted_panel(seed=7))
    fam = {c["id"]: c["family"] for c in res.candidates}
    assert fam["caffeine->sleep_quality@1"] == "primary" and fam["activity_duration->mood@1"] == "primary"
    assert fam["mood->caffeine@1"] == "exploratory" and fam["mood->energy@1"] == "exploratory"
    assert res.families["sizes"]["primary"] > 0 and res.families["sizes"]["exploratory"] > 0


def test_q_values_are_monotone_in_p_within_each_family_and_never_below_p():
    res = analyze_panel(planted_panel(seed=7))
    for fam in ("primary", "exploratory"):
        rows = sorted((c["inference"] for c in res.candidates if c["family"] == fam), key=lambda i: i["p_combined"])
        qs = [r["q_family_bh"] for r in rows]
        assert all(b >= a - 1e-12 for a, b in zip(qs, qs[1:]))
        assert all(r["q_family_bh"] >= r["p_combined"] - 1e-12 for r in rows)
        assert all(r["q_family_by"] >= r["q_family_bh"] - 1e-12 for r in rows)


def test_reported_p_is_never_more_optimistic_than_any_component_test():
    res = analyze_panel(planted_panel(seed=7))
    for c in res.candidates:
        i = c["inference"]
        comps = [v for v in (i["p_hac"], i["p_bartlett"], i["p_shift_calibrated"]) if v is not None]
        assert i["p_combined"] >= max(comps) - 1e-12


def test_missing_days_are_not_imputed_and_lags_do_not_bridge_gaps():
    T = 60
    rng = np.random.default_rng(0)
    base = rng.normal(size=T)
    x = np.where(np.arange(T) % 2 == 0, base, np.nan)               # observed on even days only
    y = np.where(np.arange(T) % 2 == 0, base + rng.normal(size=T), np.nan)
    p = panel_from_arrays({"caffeine": x, "mood": y, "energy": rng.normal(size=T)}, __import__("datetime").date(2026, 1, 5))
    res = analyze_panel(p, EngineConfig(min_pairs=10))
    ids = {c["id"] for c in res.candidates}
    assert "caffeine->mood@1" not in ids and "mood->caffeine@1" not in ids      # no day-t / day-t+1 overlap exists
    zero_lag = next(c for c in res.candidates if {c["exposure"], c["outcome"]} == {"caffeine", "mood"} and c["lag"] == 0)
    assert zero_lag["n_pairs"] == 30 and zero_lag["missingness"]["zero_imputation_used"] is False


def test_thin_data_never_reaches_a_claim():
    p = planted_panel(seed=7, T=90)
    short = p.slice(60, 74)                                          # 14 days only
    res = analyze_panel(short)
    assert all(c["tier"]["level"] <= 1 for c in res.candidates)
    assert all(c["status"] in ("INCONCLUSIVE", "TESTING") for c in res.candidates)
    one = panel_from_arrays({"mood": np.random.default_rng(0).normal(size=40)}, __import__("datetime").date(2026, 1, 5))
    assert analyze_panel(one).candidates == []


def test_runs_are_deterministic_and_receipts_change_with_data():
    p = planted_panel(seed=7)
    a, b = analyze_panel(p), analyze_panel(p)
    assert a.manifest["results_hash"] == b.manifest["results_hash"] and a.manifest["run_hash"] == b.manifest["run_hash"]
    assert a.manifest["seed"] == b.manifest["seed"]
    other = analyze_panel(planted_panel(seed=8))
    assert other.manifest["input_hash"] != a.manifest["input_hash"] and other.manifest["run_hash"] != a.manifest["run_hash"]
    assert json.dumps(a.to_dict(), sort_keys=True) == json.dumps(b.to_dict(), sort_keys=True)


def test_result_is_strictly_json_serialisable_without_nan():
    res = analyze_panel(planted_panel(seed=7))
    text = json.dumps(res.to_dict(), allow_nan=False)
    assert "NaN" not in text and len(text) > 1000


def test_effect_is_reported_in_natural_units_with_interval():
    res = analyze_panel(planted_panel(seed=7))
    c = next(c for c in res.candidates if c["id"] == "activity_duration->mood@1")
    e = c["effect"]
    assert e["beta_ci95"][0] < e["beta"] < e["beta_ci95"][1] and e["exposure_sd"] > 0 and e["outcome_sd"] > 0
    assert abs(e["effect_per_exposure_sd"] - e["beta"] * e["exposure_sd"]) < 1e-9
    assert c["bayes"]["p_non_null"] > 0.9 and abs(c["bayes"]["r_shrunk"]) <= abs(e["r_adj"]) + 1e-9


def test_sufficiency_reports_what_is_detectable():
    res = analyze_panel(planted_panel(seed=7))
    s = res.sufficiency
    assert 0 < s["mde_r_80_primary_family"] < 1 and s["median_effective_n"] > 10
    assert "effective independent days" in s["message"]


def test_diagnostics_run_only_for_candidates_that_could_reach_a_claim():
    res = analyze_panel(planted_panel(seed=7))
    with_diag = [c for c in res.candidates if c["robustness"] is not None]
    assert 0 < len(with_diag) < len(res.candidates)
    assert all(c["inference"]["q_family_bh"] <= CFG.diag_q_threshold or c["inference"]["p_combined"] <= CFG.diag_p_threshold for c in with_diag)
    assert all(c["tier"]["level"] <= 1 for c in res.candidates if c["robustness"] is None)


def test_drift_is_reported_for_each_variable_with_enough_data():
    p = planted_panel(seed=7)
    v = p.variables["energy"].copy()
    v[-8:] += 4.0                                                     # a large recent level shift
    p.variables["energy"] = v
    res = analyze_panel(p)
    d = res.drift["energy"]
    assert d["shift_detected"] or d["recent_window"]["notable"]


def test_variable_cap_bounds_the_family_deterministically_and_says_so():
    rng = np.random.default_rng(0)
    T = 60
    arrays = {f"bm:marker_{i:02d}": rng.normal(size=T) for i in range(30)}
    for k in range(5):                                   # make five variables clearly better covered
        arrays[f"bm:marker_{k:02d}"] = np.where(rng.random(T) < 0.05, np.nan, arrays[f"bm:marker_{k:02d}"])
    for k in range(5, 30):
        arrays[f"bm:marker_{k:02d}"] = np.where(rng.random(T) < 0.3, np.nan, arrays[f"bm:marker_{k:02d}"])
    p = panel_from_arrays(arrays, __import__("datetime").date(2026, 1, 5))
    cfg = EngineConfig(max_variables=8, max_diagnostic_candidates=5)
    a, b = analyze_panel(p, cfg), analyze_panel(p, cfg)
    used = {c["exposure"] for c in a.candidates} | {c["outcome"] for c in a.candidates}
    assert len(used) == 8 and {f"bm:marker_{k:02d}" for k in range(5)} <= used
    assert any(w.startswith("variable_cap_applied_kept_8") for w in a.warnings)
    assert a.manifest["results_hash"] == b.manifest["results_hash"]


def test_lag_echoes_are_labelled_not_re_tiered_and_the_brief_lists_one_finding_per_pair():
    from backend.app.research import build_brief
    res = analyze_panel(planted_panel(seed=7))
    dom = next(c for c in res.candidates if c["id"] == "activity_duration->mood@1")
    assert dom["echo_of"] is None and dom["tier"]["level"] >= 3
    echoes = [c for c in res.candidates if c.get("echo_of") == dom["id"]]
    assert echoes and set(dom["echoes"]) == {c["id"] for c in echoes}
    assert all(frozenset((c["exposure"], c["outcome"])) == frozenset(("activity_duration", "mood")) for c in echoes)
    brief = build_brief(res, limit=20)
    pairs = [frozenset(f["id"].replace("->", "@").split("@")[:2]) for f in brief["findings"]]
    assert len(pairs) == len(set(pairs))                                  # no pair listed twice
    top = next(f for f in brief["findings"] if f["id"] == dom["id"])
    assert top["also_seen_at"] == dom["echoes"] and "persistent" in top["echo_note"]
