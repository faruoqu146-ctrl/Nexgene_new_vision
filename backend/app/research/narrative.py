"""Plain-language research brief. Wording is a function of the evidence tier, never of enthusiasm.

The language rules (enforced by tests):
  * ERL-1/2 say "associated"; ERL-3 says "tends to be followed by"; only ERL-5 describes an
    experiment result, and only for this person and period.
  * No sentence recommends treatment or interprets a finding as a diagnosis.
"""
from __future__ import annotations

import math
from typing import Optional

from .config import LOW_CONTROLLABILITY, RANDOMIZABLE_EXPOSURES, label, unit
from .experiment import design_power


def _lag_text(lag: int) -> str:
    return "on the same day" if lag == 0 else ("the next day" if lag == 1 else f"{lag} days later")


def _fmt(v: Optional[float], nd: int = 2) -> str:
    return "n/a" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.{nd}f}"


def _q_clause(q: Optional[float]) -> str:
    if q is None or not math.isfinite(q):
        return "is n/a"
    return "< 0.001" if q < 0.001 else f"= {q:.3f}"


def _lag_label(lag: int) -> str:
    return "same day" if lag == 0 else ("next day" if lag == 1 else f"{lag} days later")


def alternatives_for(c: dict) -> list:
    alts = [
        "A third factor (for example workload, illness, or travel) may influence both variables.",
        "A weekly rhythm or slow drift shared by both variables may remain after adjustment.",
        "Days with missing entries may differ systematically from logged days.",
        "A few unusual days or weeks may drive the association.",
    ]
    if c["lag"] == 0:
        alts.insert(0, "Same-day measurements share context, so either variable may be responding to the other.")
    else:
        alts.insert(0, "The outcome may influence later exposure (reverse direction) or both may follow a common cause.")
    return alts


def rationale_for(c: dict) -> str:
    x, y, lag = label(c["exposure"]), label(c["outcome"]), c["lag"]
    if lag:
        return (f"{x} on one day is compared with {y} {_lag_text(lag)} after removing weekday pattern and linear trend. "
                "Temporal order is supportive context, not proof of causation.")
    return f"{x} and {y} are compared on the same days after removing weekday pattern and linear trend; direction is not identifiable."


def prediction_text(c: dict) -> str:
    x, y, lag = label(c["exposure"]), label(c["outcome"]), c["lag"]
    sign = c["effect"]["r_adj"] > 0
    hi = "higher" if sign else "lower"
    if lag:
        return f"When {x} is higher than your recent norm, {y} is expected to be {hi} than your recent norm {_lag_text(lag)}."
    return f"On days when {x} is higher than your recent norm, {y} is expected to be {hi} than your recent norm."


def describe_candidate(c: dict, track: Optional[dict] = None, experiment: Optional[dict] = None) -> dict:
    x, y, lag = c["exposure"], c["outcome"], c["lag"]
    lx, ly = label(x), label(y)
    e, inf_, b = c["effect"], c["inference"], c["bayes"]
    tier = c["tier"]["level"]
    sd_x, ux, uy = e.get("exposure_sd"), unit(x), unit(y)
    per_sd = e.get("effect_per_exposure_sd")
    more_less = "higher" if (per_sd or e["r_adj"]) > 0 else "lower"
    if per_sd is not None and sd_x:
        eff = (f"A one-standard-deviation higher {lx} (about {sd_x:.1f} {ux}) goes with {abs(per_sd):.2f} {uy} {more_less} {ly} {_lag_text(lag)} "
               f"(adjusted r = {e['r_adj']:+.2f}, 95% interval {_fmt(e['r_ci95'][0])} to {_fmt(e['r_ci95'][1])}).")
    else:
        eff = f"Adjusted r = {e['r_adj']:+.2f} between {lx} and {ly} {_lag_text(lag)}."
    if tier == 0:
        head = f"No usable signal yet between {lx} and {ly}." if c["tier"].get("reason") == "no_detectable_signal" else f"Not enough data yet to assess {lx} and {ly}."
    elif tier == 1:
        head = f"Weak, unconfirmed signal: {lx} and {ly} ({_lag_label(lag)})."
    elif tier == 2:
        head = f"{lx.capitalize()} and {ly} are robustly associated in your data."
    elif tier == 3:
        head = f"Higher {lx} tends to be followed by {more_less} {ly} {_lag_text(lag)}, beyond {ly}'s own pattern."
    elif tier == 4:
        head = f"A locked model of {lx} and {ly} predicted new days better than a no-effect model."
    else:
        head = f"A randomised self-experiment supports an effect of {lx} on {ly} for you."
    if c["status"] == "FALSIFIED":
        head = f"A randomised self-experiment did not support the {lx} and {ly} relationship."
    if c["status"] == "WEAKENED":
        head = f"The {lx} and {ly} relationship is weakening: forward predictions are failing."
    evid = (f"Family-adjusted q {_q_clause(inf_['q_family_bh'])} across {inf_['family_size']} {inf_['family']} hypotheses; "
            f"posterior probability the association is non-zero = {_fmt(100 * b['p_non_null'], 0)}%; "
            f"shrunk (winner's-curse-corrected) r = {b['r_shrunk']:+.2f}.")
    caveats = ["This is observational and does not show that one thing causes the other."]
    sens = (c.get("sensitivity") or {}).get("unmeasured_confounding")
    if sens:
        caveats.append(f"An unmeasured factor would need to be associated with both variables by a risk-ratio of about "
                       f"{sens['e_value']:.1f} to fully explain this away.")
    if lag == 0:
        caveats.append("Same-day associations cannot reveal which variable leads.")
    dt = c.get("directional_test")
    if dt and dt.get("evaluable") and dt.get("reverse_significant"):
        caveats.append("The reverse direction is also predictive, which suggests feedback or a common cause.")
    out = {"id": c["id"], "tier": c["tier"]["code"], "tier_label": c["tier"]["label"], "status": c["status"],
           "headline": head, "effect": eff, "evidence": evid, "caveats": caveats, "falsifiers": c.get("falsifiers", [])}
    if track and track.get("scored_days"):
        out["forward_test"] = (f"Locked-model forward test: evidence ratio {track['evidence_ratio']:.1f} over {track['scored_days']} unseen days "
                               f"({track['hits']} hits / {track['misses']} misses on informative days).")
    if experiment and experiment.get("verdict"):
        out["experiment"] = f"Self-experiment verdict: {experiment['verdict']}."
    return out


def next_experiments(result, limit: int = 3) -> list:
    """Rank candidate self-experiments by expected usefulness and feasibility (transparent heuristic)."""
    ranked = []
    prof = result.quality.get("variables", {})
    for c in result.candidates:
        if c["tier"]["level"] < 2 or c["tier"]["level"] >= 5 or c["status"] in ("FALSIFIED",):
            continue
        x, y = c["exposure"], c["outcome"]
        if x not in RANDOMIZABLE_EXPOSURES:
            continue
        sd_y = prof.get(y, {}).get("sd")
        rho = prof.get(y, {}).get("acf1")
        shrink = abs(c["bayes"]["r_shrunk"] / c["effect"]["r_adj"]) if c["effect"]["r_adj"] else 0.0
        eff_sd = c["effect"].get("effect_per_exposure_sd")
        expected = abs(eff_sd) * min(1.0, shrink) if eff_sd else None
        pw = design_power(outcome_sd=sd_y, rho=rho, n_blocks=14, period_len=1, effect=expected)
        need = pw.get("blocks_needed_for_effect") if pw.get("available") else None
        feas = 0.0 if need is None else min(1.0, 21.0 / need)
        ctrl = 0.6 if x in LOW_CONTROLLABILITY else 1.0
        score = c["bayes"]["p_practical"] * ctrl * feas
        ranked.append((score, {
            "candidate_id": c["id"], "exposure": x, "outcome": y, "lag": c["lag"],
            "why": f"{c['tier']['code']} association; probability of a practically meaningful effect {c['bayes']['p_practical']:.0%}.",
            "expected_effect_outcome_units": expected, "blocks_needed": need, "days_needed": None if need is None else need * 2,
            "feasible_in_8_weeks": bool(need is not None and need * 2 <= 56), "controllability": "partial" if x in LOW_CONTROLLABILITY else "good",
            "score": round(score, 3),
        }))
    ranked.sort(key=lambda t: -t[0])
    return [r for _, r in ranked[:limit]]


def build_brief(result, tracks: Optional[dict] = None, experiments: Optional[dict] = None, limit: int = 6) -> dict:
    tracks, experiments = tracks or {}, experiments or {}
    top = [c for c in result.candidates if c["tier"]["level"] >= 1 and not c.get("echo_of")][:limit]
    findings = []
    for c in top:
        d = describe_candidate(c, tracks.get(c["id"]), experiments.get(c["id"]))
        if c.get("echoes"):
            d["also_seen_at"] = list(c["echoes"])
            d["echo_note"] = "Weaker associations on the same pair at other lags or in the reverse direction are expected when series are persistent; they are not listed separately."
        findings.append(d)
    alerts = []
    for name, d in result.drift.items():
        rw = d.get("recent_window") or {}
        if d.get("shift_detected") or rw.get("notable"):
            alerts.append({
                "variable": name, "direction": d.get("direction") or rw.get("direction"),
                "message": (f"Your {label(name)} has been {d.get('direction') or rw.get('direction')} than your usual baseline recently "
                            f"(latest value {d['latest_value']:.1f} vs baseline {d['baseline_center']:.1f} {unit(name)})."),
                "method": "CUSUM / recent-window test on a robust personal baseline", "since": d.get("onset_date"),
            })
    levels = [c["tier"]["level"] for c in result.candidates]
    status = "active" if findings else ("baseline_forming" if result.candidates or result.drift else "starting")
    return {
        "status": status, "findings": findings, "baseline_alerts": alerts, "next_experiments": next_experiments(result),
        "sufficiency": result.sufficiency, "data_quality": {k: result.quality[k] for k in ("score", "components", "active_days", "active_weeks", "warnings")},
        "tier_counts": {f"ERL-{k}": levels.count(k) for k in range(6)},
        "clinical_escalation": "not_assessed",
        "limitations": [
            "These are personal observational patterns, not diagnoses or treatment advice.",
            "Evidence tiers describe how a claim was tested, not how important it is.",
        ],
    }

