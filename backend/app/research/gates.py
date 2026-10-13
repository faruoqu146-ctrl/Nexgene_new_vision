"""Evidence gates: explicit go / no-go checks that decide the Evidence Readiness Level.

Every claim the engine makes is the output of named gates, each with a pass/fail and
the numbers behind it, so a reviewer can see exactly why a relationship holds the
level it holds. Gates can only be passed by data; none can be satisfied by wording.
"""
from __future__ import annotations

from typing import Optional

from .config import ERL, STATUS_BY_TIER, EngineConfig


def _gate(gid: str, passed: Optional[bool], detail: str, required_for: int) -> dict:
    return {"id": gid, "passed": passed, "detail": detail, "required_for_tier": required_for}


def evaluate_gates(cand: dict, cfg: EngineConfig, *, prior: Optional[dict] = None,
                   track: Optional[dict] = None, experiment: Optional[dict] = None) -> dict:
    """Compute tier, status and gate table for one candidate (dict as built by discovery)."""
    inf, eff = cand["inference"], cand["effect"]
    n, weeks = cand["n_pairs"], cand["active_weeks"]
    miss = cand["missingness"].get("pair_missingness_rate")
    rob = cand.get("robustness")
    dirx = cand.get("directional_test")
    gates = []

    enough_for_test = n >= cfg.min_pairs
    g_data = (n >= cfg.min_pairs_support and weeks >= cfg.min_active_weeks
              and (miss is None or miss <= cfg.max_pair_missingness))
    gates.append(_gate("data_sufficiency", g_data,
                       f"{n} paired days (need >= {cfg.min_pairs_support}), {weeks} active weeks (need >= {cfg.min_active_weeks}), "
                       f"pair missingness {'n/a' if miss is None else format(miss, '.0%')} (max {cfg.max_pair_missingness:.0%})", 2))
    q = inf["q_family_bh"]
    g_sig = q is not None and q <= cfg.alpha_q
    gates.append(_gate("false_discovery_control", g_sig,
                       f"family-adjusted q = {q:.4f} (need <= {cfg.alpha_q})" if q is not None else "not evaluated", 2))
    g_eff = abs(eff["r_adj"]) >= cfg.effect_floor_r
    gates.append(_gate("practical_effect_size", g_eff, f"|adjusted r| = {abs(eff['r_adj']):.2f} (need >= {cfg.effect_floor_r})", 2))
    if rob is None:
        g_rob = None
        gates.append(_gate("robustness", None, "diagnostics not run (candidate did not pass screening)", 2))
    else:
        g_rob = bool(rob.get("robust"))
        gates.append(_gate("robustness", g_rob,
                           f"sign-consistent across analyses: {rob.get('sign_consistent')}; outlier-stable: {rob.get('outlier_stable')}; "
                           f"high-pass consistent: {rob.get('highpass_consistent')}", 2))

    # prior concordance (optional)
    if prior and prior.get("review_status") == "reviewed":
        sign = 1 if eff["r_adj"] > 0 else -1
        g_prior = sign == prior.get("expected_sign")
        gates.append(_gate("prior_concordance", g_prior,
                           f"reviewed prior expected_sign={prior.get('expected_sign')}; observed sign={sign}", 2))
    else:
        gates.append(_gate("prior_concordance", None, "no reviewed prior available", 2))

    # decide tier 0-2
    tier = 0
    reason = "insufficient data for a formal test"
    if enough_for_test:
        tier = 1
        reason = "testable but not yet meeting ERL-2 gates"
    if g_data and g_sig and g_eff and (g_rob is None or g_rob):
        tier = 2
        reason = "observational association that clears the primary gates"

    # temporal order (tier 3)
    if cand.get("lag", 0) > 0:
        if dirx and dirx.get("evaluable"):
            fwd = dirx.get("forward") or {}
            g_dir = (fwd.get("p") is not None and fwd["p"] <= cfg.directional_alpha and not dirx.get("reverse_significant"))
            gates.append(_gate("temporal_order", g_dir,
                               f"forward partial r = {fwd.get('r_partial', 0):.2f} (p={fwd.get('p', 1):.4f}, need <= {cfg.directional_alpha}); reverse significant: {dirx.get('reverse_significant')}", 3))
            if tier == 2 and g_dir:
                tier = 3
        else:
            gates.append(_gate("temporal_order", None, "AR-controlled directional test not evaluable with the available days", 3))
    else:
        gates.append(_gate("temporal_order", None, "same-day pair: direction is not identifiable from observational data", 3))

    # prospective validation (tier 4)
    if track and track.get("scored_days", 0) > 0:
        er = track["evidence_ratio"]
        g_pro = (er >= cfg.evidence_ratio_confirm and track.get("informative_days", 0) >= cfg.forecast_min_informative_days)
        gates.append(_gate("prospective_validation", g_pro,
                           f"locked-model evidence ratio {er:.1f} over {track['scored_days']} unseen days "
                           f"(need >= {cfg.evidence_ratio_confirm:g} and >= {cfg.forecast_min_informative_days} informative days)", 4))
        if tier >= 2 and g_pro:
            tier = max(tier, 4)
    else:
        gates.append(_gate("prospective_validation", None, "no completed locked-model forward test yet", 4))

    # experiment (tier 5)
    if experiment and experiment.get("verdict"):
        v = experiment["verdict"]
        gates.append(_gate("randomised_experiment", v == "SUPPORTED",
                           f"pre-registered N-of-1 experiment verdict: {v}", 5))
        if v == "SUPPORTED":
            tier = 5
    else:
        gates.append(_gate("randomised_experiment", None, "no completed randomised self-experiment", 5))

    status = STATUS_BY_TIER[tier]
    notes = []
    if experiment and experiment.get("verdict") in ("REFUTED", "CONTRADICTED"):
        status, tier = "FALSIFIED", min(tier, 1)
        notes.append("A pre-registered randomised experiment did not support this relationship.")
    elif track and track.get("scored_days", 0) > 0 and track["evidence_ratio"] <= cfg.evidence_ratio_weaken \
            and track.get("informative_days", 0) >= cfg.forecast_min_informative_days:
        status, tier = "WEAKENED", min(tier, 2)
        notes.append("The locked model predicted new days worse than a no-effect model.")
    code, label, meaning = ERL[tier]
    return {
        "tier": {"level": tier, "code": code, "label": label, "meaning": meaning, "reason": reason},
        "status": status, "gates": gates, "notes": notes,
    }
