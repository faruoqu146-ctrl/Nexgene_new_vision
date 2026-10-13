"""Hypothesis discovery over a personal longitudinal panel.

Pipeline (every step deterministic given the input data hash):

  1. Profile every variable; keep only eligible ones (enough days, real variation).
  2. Build the *whole* candidate family: same-day pairs (undirected) and lagged pairs
     (directed), split into a pre-specified PRIMARY family (modifiable behaviour ->
     state) and an EXPLORATORY family (everything else). No effect-size prefilter.
  3. Screen every candidate with calibrated inference (weekday/trend-adjusted partial
     correlation, shift-calibrated empirical null, HAC, Bartlett; conservative max).
  4. Control the false-discovery rate *within each family* over all tested candidates.
  5. Empirical-Bayes shrinkage across the family (winner's-curse correction).
  6. Run expensive diagnostics only for candidates that could plausibly reach a claim.
  7. Evaluate explicit evidence gates -> Evidence Readiness Level (ERL) and status.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from . import inference as inf
from .bayes import bf_label, default_prior_summary, fit_two_group, posterior
from .config import BEHAVIOR_EXPOSURES, DEFAULT_CONFIG, ENGINE_NAME, ENGINE_VERSION, MODEL_VERSION, STATE_OUTCOMES, EngineConfig
from .gates import evaluate_gates
from .multiplicity import bh_adjust, by_adjust, holm_adjust, storey_pi0
from .panel import Panel, panel_quality
from .provenance import derive_seed, make_manifest, results_digest, to_jsonable
from .spc import analyze_drift

LIMITATIONS = [
    "Observational associations in one person's self-tracked data; they do not establish causation, diagnosis, or treatment effects.",
    "Same-day associations cannot reveal direction. Only a randomised self-experiment (ERL-5) approaches causal evidence, and then only for that person and period.",
    "Findings describe this person's recent data and may not generalise to other people or other periods.",
    "Self-reported scales are ordinal and may be reported inconsistently; missing days are never imputed.",
    "Error-rate guarantees were measured on synthetic data (see the validation report); they have not been validated on real cohorts.",
]


@dataclass
class ResearchResult:
    candidates: list
    families: dict
    quality: dict
    drift: dict
    sufficiency: dict
    manifest: dict
    config: dict
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return to_jsonable({
            "engine": ENGINE_NAME, "engine_version": ENGINE_VERSION, "model_version": MODEL_VERSION,
            "candidates": self.candidates, "families": self.families, "quality": self.quality,
            "drift": self.drift, "sufficiency": self.sufficiency, "manifest": self.manifest,
            "config": self.config, "warnings": self.warnings, "limitations": LIMITATIONS,
        })

    def top(self, n: int = 10, min_tier: int = 1) -> list:
        return [c for c in self.candidates if c["tier"]["level"] >= min_tier][:n]


def _orient(a: str, b: str):
    """Orient an undirected same-day pair as (exposure, outcome) using the variable taxonomy."""
    a_beh, b_beh = a in BEHAVIOR_EXPOSURES, b in BEHAVIOR_EXPOSURES
    if a_beh and not b_beh:
        return a, b
    if b_beh and not a_beh:
        return b, a
    return tuple(sorted((a, b)))


def _family(exposure: str, outcome: str) -> str:
    return "primary" if exposure in BEHAVIOR_EXPOSURES and outcome in STATE_OUTCOMES else "exploratory"


def _first_last(mask: np.ndarray):
    idx = np.flatnonzero(mask)
    return (int(idx[0]), int(idx[-1])) if len(idx) else (None, None)


def _missingness(mask_x: np.ndarray, mask_y: np.ndarray, lag: int, pair_idx: np.ndarray) -> dict:
    """Missingness inside the span where both variables could have been observed. No imputation."""
    T = len(mask_x)
    fx, lx = _first_last(mask_x)
    fy, ly = _first_last(mask_y)
    if fx is None or fy is None:
        return {"expected_pair_days": 0, "observed_pair_days": 0, "missing_pair_days": 0, "pair_missingness_rate": None,
                "exposure_missingness_rate": None, "outcome_missingness_rate": None, "longest_pair_gap_days": 0,
                "zero_imputation_used": False}
    start, end = max(fx, fy - lag), min(lx, ly - lag, T - 1 - lag)
    if end < start:
        return {"expected_pair_days": 0, "observed_pair_days": int(len(pair_idx)), "missing_pair_days": 0,
                "pair_missingness_rate": None, "exposure_missingness_rate": None, "outcome_missingness_rate": None,
                "longest_pair_gap_days": 0, "zero_imputation_used": False}
    expected = end - start + 1
    have = np.zeros(expected, dtype=bool)
    sel = pair_idx[(pair_idx >= start) & (pair_idx <= end)] - start
    have[sel] = True
    observed = int(have.sum())
    best = run = 0
    for ok in have:
        run = 0 if ok else run + 1
        best = max(best, run)
    xs = mask_x[start: end + 1]
    ys = mask_y[start + lag: end + lag + 1]
    return {
        "expected_pair_days": int(expected), "observed_pair_days": observed, "missing_pair_days": int(expected - observed),
        "pair_missingness_rate": (expected - observed) / expected, "exposure_missingness_rate": float(1 - xs.mean()),
        "outcome_missingness_rate": float(1 - ys.mean()), "longest_pair_gap_days": int(best), "zero_imputation_used": False,
    }


def _week_ids(panel: Panel) -> np.ndarray:
    out = np.zeros(panel.T, dtype=np.int64)
    for i, d in enumerate(panel.dates):
        y, w, _ = d.isocalendar()
        out[i] = y * 100 + w
    return out


def _cand_rng(seed: int, cid: str) -> np.random.Generator:
    h = int(hashlib.sha256(cid.encode()).hexdigest()[:8], 16)
    return np.random.default_rng(np.random.SeedSequence([seed, h]))


def analyze_panel(
    panel: Panel,
    cfg: EngineConfig = DEFAULT_CONFIG,
    *,
    priors: Optional[dict] = None,
    tracks: Optional[dict] = None,
    experiments: Optional[dict] = None,
    prev_run_hash: Optional[str] = None,
) -> ResearchResult:
    """Run the full discovery pipeline on a panel and return a :class:`ResearchResult`.

    ``priors``: {(exposure, outcome): {expected_sign, review_status, citations}} (only reviewed priors act).
    ``tracks``: {candidate_id: forward-test summary}; ``experiments``: {candidate_id: experiment summary}.
    """
    priors, tracks, experiments = priors or {}, tracks or {}, experiments or {}
    digest = panel.digest()
    seed = derive_seed(digest, cfg.seed)
    quality = panel_quality(panel, cfg)
    warnings = list(quality["warnings"])
    eligible = sorted(quality["eligible_variables"])
    window = {"start": panel.window_start.isoformat(), "end": panel.window_end.isoformat(), "days": panel.T, "tz": panel.tz}

    def _empty(reason: str) -> ResearchResult:
        res = ResearchResult([], {}, quality, {}, {"readiness": reason, "message": reason}, {}, cfg.to_dict(), warnings)
        res.manifest = make_manifest(panel_digest=digest, config_digest=cfg.digest(), seed=seed,
                                     results_hash=results_digest([]), prev_run_hash=prev_run_hash, window=window)
        return res

    if len(eligible) < 2:
        return _empty("Fewer than two variables have enough varied observations to analyse.")

    if len(eligible) > cfg.max_variables:
        ranked = sorted(eligible, key=lambda n: (-quality["variables"][n]["n_days"], n))
        dropped = sorted(ranked[cfg.max_variables:])
        eligible = sorted(ranked[: cfg.max_variables])
        warnings.append(f"variable_cap_applied_kept_{cfg.max_variables}_dropped_{','.join(dropped)}")
    D = inf.build_design(panel.ordinals, panel.weekdays)
    prepared = {name: inf.prepare_variable(name, panel.variables[name], D, cfg) for name in eligible}
    kernel = inf.NullKernel(panel.T, max(cfg.lags), cfg.shift_buffer)
    week_ids = _week_ids(panel)

    # ---- 1. candidate family and screening --------------------------------
    specs = []
    for lag in cfg.lags:
        if lag == 0:
            for i, a in enumerate(eligible):
                for b in eligible[i + 1:]:
                    x, y = _orient(a, b)
                    specs.append((x, y, 0))
        else:
            for x in eligible:
                for y in eligible:
                    if x != y:
                        specs.append((x, y, lag))
    specs.sort(key=lambda s: (0 if _family(s[0], s[1]) == "primary" else 1, s[2], s[0], s[1]))
    if len(specs) > cfg.max_candidates:
        warnings.append(f"candidate_family_truncated_to_{cfg.max_candidates}")
        specs = specs[: cfg.max_candidates]

    screened = []
    for (x, y, lag) in specs:
        s = inf.screen_pair(prepared[x], prepared[y], lag, kernel, cfg)
        if s is not None:
            screened.append((x, y, lag, s))
    if not screened:
        return _empty("No variable pair has enough overlapping days to test yet.")

    # ---- 2. multiplicity within each family -------------------------------
    fam_of = [_family(x, y) for (x, y, _, _) in screened]
    q_bh = np.ones(len(screened))
    q_by = np.ones(len(screened))
    holm = np.ones(len(screened))
    fam_sizes = {}
    for fam in ("primary", "exploratory"):
        idx = [i for i, f in enumerate(fam_of) if f == fam]
        fam_sizes[fam] = len(idx)
        if idx:
            p = np.array([screened[i][3].p_combined for i in idx])
            q_bh[idx], q_by[idx], holm[idx] = bh_adjust(p), by_adjust(p), holm_adjust(p)
    q_global = bh_adjust(np.array([s.p_combined for (_, _, _, s) in screened]))

    # ---- 3. empirical Bayes across the whole family ----------------------
    zs = np.array([inf.fisher_z(s.r_adj) for (_, _, _, s) in screened])
    ses = np.array([s.se_z for (_, _, _, s) in screened])
    eb = fit_two_group(zs, ses)
    p_all = np.array([s.p_combined for (_, _, _, s) in screened])
    pi0_storey = storey_pi0(p_all)

    # ---- 4. which candidates get the expensive diagnostics ----------------
    order = np.argsort(p_all, kind="mergesort")
    diag_ids = set()
    for i in order:
        if len(diag_ids) >= cfg.max_diagnostic_candidates:
            break
        if q_bh[i] <= cfg.diag_q_threshold or p_all[i] <= cfg.diag_p_threshold:
            diag_ids.add(int(i))

    candidates = []
    for i, (x, y, lag, s) in enumerate(screened):
        cid = f"{x}->{y}@{lag}"
        px, py = prepared[x], prepared[y]
        pair_week = len({int(week_ids[j]) for j in s.day_idx})
        miss = _missingness(~np.isnan(panel.variables[x]), ~np.isnan(panel.variables[y]), lag, s.day_idx)
        r_lo, r_hi = s.r_ci(0.95)
        sd_ratio = (s.sd_y_resid / s.sd_x_resid) if s.sd_x_resid > 0 else float("nan")
        exp_sd = px.sd_raw
        effect = {
            "r_raw": s.r_raw, "r_adj": s.r_adj, "r_ci95": [r_lo, r_hi],
            "beta": s.beta, "beta_ci95": [r_lo * sd_ratio, r_hi * sd_ratio],
            "effect_per_exposure_sd": s.beta * exp_sd if exp_sd else None,
            "exposure_sd": exp_sd, "outcome_sd": py.sd_raw,
            "adjustment": "weekday indicators + linear trend (partial correlation)",
        }
        inference = {
            "p_combined": s.p_combined, "p_method": s.p_method, "p_hac": s.p_hac, "p_bartlett": s.p_eff,
            "p_shift_calibrated": s.p_shift_gauss, "p_shift_rank": s.p_shift_rank,
            "q_family_bh": float(q_bh[i]), "q_family_by": float(q_by[i]), "p_holm_family": float(holm[i]),
            "q_global_bh": float(q_global[i]), "family": fam_of[i], "family_size": fam_sizes[fam_of[i]],
            "n_eff": s.n_eff, "n_eff_bartlett": s.n_eff_bartlett, "rms_null": s.rms_null, "n_shifts": s.n_shifts,
            "se_z": s.se_z,
        }
        post = posterior(float(zs[i]), float(ses[i]), eb["pi0"], eb["tau"])
        dp = default_prior_summary(float(zs[i]), float(ses[i]), cfg.bayes_prior_sd_z, math.atanh(cfg.rope_r))
        m_ = dp["posterior_mean_z"]
        sd_ = dp["posterior_sd_z"]
        bayes = {
            "p_non_null": post["p_non_null"], "local_fdr": post["lfdr"], "r_shrunk": math.tanh(post["z_shrunk"]),
            "family_pi0": eb["pi0"], "family_tau": eb["tau"],
            "log10_bf10": dp["log10_bf10"], "bf_label": bf_label(dp["log10_bf10"]), "p_direction": dp["p_direction"],
            "p_practical": dp["p_practical"], "r_cred95_default_prior": [math.tanh(m_ - 1.96 * sd_), math.tanh(m_ + 1.96 * sd_)],
            "default_prior_sd_z": cfg.bayes_prior_sd_z,
        }
        cand = {
            "id": cid, "exposure": x, "outcome": y, "lag": lag, "is_directional": lag > 0, "family": fam_of[i],
            "n_pairs": s.n, "active_weeks": pair_week, "missingness": miss, "effect": effect, "inference": inference,
            "bayes": bayes, "robustness": None, "directional_test": None, "sensitivity": None,
        }
        ratio = s.n_eff / s.n if s.n else 0.0
        fam_m = max(1, fam_sizes[fam_of[i]])
        r_post = abs(bayes["r_shrunk"])
        cand["power"] = {
            "n_eff": s.n_eff, "mde_r_80_single_test": inf.minimum_detectable_r(s.n_eff, 0.05, 0.80),
            "mde_r_80_family_bonferroni": inf.minimum_detectable_r(s.n_eff, 0.05 / fam_m, 0.80),
            "days_to_confirm_80": inf.days_needed(r_post, ratio, 0.05, 0.80) if r_post >= 0.05 else None,
            "basis": "shrunk effect estimate, single pre-registered confirmatory test at alpha 0.05",
        }
        if i in diag_ids:
            rng = _cand_rng(seed, cid)
            cand["robustness"] = inf.robustness(px, py, s, week_ids, rng, cfg)
            cand["directional_test"] = inf.directional_diagnostics(px, py, D, lag, kernel, cfg)
            cand["sensitivity"] = {"unmeasured_confounding": inf.e_value(s.r_adj, (r_lo, r_hi))}
        candidates.append(cand)

    # ---- 5. gates -> tiers -------------------------------------------------
    for cand in candidates:
        verdict = evaluate_gates(
            cand, cfg,
            prior=priors.get((cand["exposure"], cand["outcome"])), track=tracks.get(cand["id"]),
            experiment=experiments.get(cand["id"]),
        )
        cand["tier"], cand["status"], cand["gates"], cand["notes"] = verdict["tier"], verdict["status"], verdict["gates"], verdict["notes"]
        if cand["tier"]["level"] >= 1:
            cand["falsifiers"] = _falsifiers(cand)
    candidates.sort(key=lambda c: (-c["tier"]["level"], c["inference"]["q_family_bh"], -abs(c["effect"]["r_adj"])))
    _annotate_echoes(candidates)

    # ---- 6. drift, sufficiency, manifest ---------------------------------
    drift = {}
    for name in eligible:
        d = analyze_drift(panel.variables[name], panel.dates, cfg)
        if d.get("evaluable"):
            drift[name] = d
    n_effs = [c["power"]["n_eff"] for c in candidates]
    med_neff = float(np.median(n_effs)) if n_effs else 0.0
    suff = {
        "variables_eligible": len(eligible), "candidates_tested": len(candidates), "family_sizes": fam_sizes,
        "median_effective_n": med_neff,
        "mde_r_80_primary_family": inf.minimum_detectable_r(med_neff, 0.05 / max(1, fam_sizes.get("primary", 0)), 0.80) if fam_sizes.get("primary") else None,
        "mde_r_80_exploratory_family": inf.minimum_detectable_r(med_neff, 0.05 / max(1, fam_sizes.get("exploratory", 0)), 0.80) if fam_sizes.get("exploratory") else None,
        "pi0_empirical_bayes": eb["pi0"], "pi0_storey": pi0_storey, "active_days": quality["active_days"],
        "active_weeks": quality["active_weeks"],
    }
    mp = suff["mde_r_80_primary_family"]
    suff["message"] = (
        f"With about {med_neff:.0f} effective independent days, a single pre-specified relationship must have |r| of roughly "
        f"{mp:.2f} or more to be detected reliably after correcting for {fam_sizes.get('primary', 0)} primary hypotheses. "
        "Weaker real effects need more days or a targeted self-experiment." if mp else "Not enough data to quantify detectable effect sizes yet."
    )
    suff["readiness"] = "adequate" if (quality["active_weeks"] >= cfg.min_active_weeks and med_neff >= 20) else "building"
    res = ResearchResult(candidates, {"sizes": fam_sizes, "empirical_bayes": eb, "pi0_storey": pi0_storey}, quality, drift, suff, {}, cfg.to_dict(), warnings)
    res.manifest = make_manifest(panel_digest=digest, config_digest=cfg.digest(), seed=seed,
                                 results_hash=results_digest(candidates), prev_run_hash=prev_run_hash, window=window)
    return res


def _annotate_echoes(candidates: list) -> None:
    """Flag candidates that are probably lag/orientation echoes of a stronger candidate on the same variable pair.

    Persistent series make a real relationship show up, weaker, at neighbouring lags and in the reverse orientation.
    Those associations are statistically genuine, not false discoveries, but listing each as a separate finding is
    misleading. Tiers are NOT changed; this only labels. ``candidates`` must already be sorted best-first.
    """
    seen: dict = {}
    for c in candidates:
        c["echo_of"], c["echoes"] = None, []
        if c["tier"]["level"] < 1:
            continue
        key = frozenset((c["exposure"], c["outcome"]))
        if key not in seen:
            seen[key] = c
        else:
            c["echo_of"] = seen[key]["id"]
            seen[key]["echoes"].append(c["id"])


def _falsifiers(cand: dict) -> list:
    lag = cand["lag"]
    f = [
        "The adjusted association shrinks toward zero or reverses in the next 3-4 weeks of data.",
        "A locked-model forecast on unseen days performs no better than a model that assumes no effect.",
        "A randomised self-experiment (assigning the exposure by schedule) shows no difference in the outcome.",
        "Removing a handful of unusual days or whole weeks removes the association.",
    ]
    if lag >= 1:
        f.append("The outcome predicts the later exposure at least as well as the exposure predicts the later outcome.")
    return f
