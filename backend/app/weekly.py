"""Evidence-gated weekly report assembly.

Pipeline (every step is deterministic; no language model is involved):

  1. bucket authorised observations by EVENT day (see ``temporal``)
  2. compute coverage and quarantine counts
  3. run descriptive comparisons against a baseline that EXCLUDES the current week,
     each behind an explicit evidence gate
  4. adapt eligible research-engine results (never invent them) and describe the engine state
  5. emit a versioned report contract in which every finding names its type and evidence

Finding types are not interchangeable:

  descriptive_summary    a calculation over recorded data (no relationship implied)
  insufficient_evidence  says exactly what is missing before a statement can be made
  hypothesis             ERL-1 engine signal; still consistent with chance
  candidate_association  ERL-2/3 engine result; observational, no causation
  validated_finding      ERL-4/5 engine result (prospectively confirmed / experimental)

The weekly path itself NEVER emits an association: recording two variables in the same week
establishes only that both were recorded.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, median, stdev
from typing import Iterable, Optional

try:
    from .temporal import Bucketed, ReportingWindow, as_utc, bucket_observations, weekly_window
except ImportError:  # pragma: no cover - executed as a script from backend/app
    from temporal import Bucketed, ReportingWindow, as_utc, bucket_observations, weekly_window

SCHEMA_VERSION = "nexgene.weekly_report/1"
ALGORITHM_VERSION = "weekly-descriptive/2"

MIN_WEEK_DAYS = 3        # distinct local days with the variable in the current week
MIN_BASELINE_DAYS = 4    # distinct local days with the variable in the baseline
MAX_DESCRIPTIVE_FINDINGS = 3
MAX_ENGINE_FINDINGS = 2

ENGINE_TTL = timedelta(days=7)
RUN_STALE_AFTER = timedelta(minutes=15)

CHANGE_RULES = {
    "sleep_duration": {"label": "sleep duration", "unit": " h", "min_delta": 0.5},
    "sleep_quality": {"label": "sleep quality", "unit": "/10", "min_delta": 1.0},
    "energy": {"label": "energy", "unit": "/10", "min_delta": 1.0},
    "mood": {"label": "mood", "unit": "/10", "min_delta": 1.0},
    "stress": {"label": "stress", "unit": "/10", "min_delta": 1.0},
    "focus": {"label": "focus", "unit": "/10", "min_delta": 1.0},
}

DISCLAIMER = "This report describes patterns in your recorded data. It is not a diagnosis or medical advice."
STANDING_LIMITATIONS = [
    "Self-reported check-ins are coarse and subjective.",
    "A difference between two periods does not show why it happened.",
]

# ERL tier (research engine evidence ladder) -> report finding type.
TIER_TYPE = {1: "hypothesis", 2: "candidate_association", 3: "candidate_association",
             4: "validated_finding", 5: "validated_finding"}
ELIGIBLE_HYPOTHESIS_STATUS = {"TESTING", "SUPPORTED", "CONFIRMED"}


def _pretty(name: str) -> str:
    return str(name).replace("_", " ")


def _daily_means(items: Iterable, kind: str) -> dict:
    buckets = defaultdict(list)
    for o in items:
        if o.kind == kind and o.value_numeric is not None:
            buckets[o.day].append(o.value_numeric)
    return {d: mean(v) for d, v in buckets.items()}


def analyse_kind(week: list, baseline: list, kind: str) -> dict:
    """Apply the evidence gate for one variable. Returns a status and every number used."""
    rule = CHANGE_RULES[kind]
    w, b = _daily_means(week, kind), _daily_means(baseline, kind)
    out = {"kind": kind, "week_days": len(w), "baseline_days": len(b), "status": "no_week_data"}
    if not w:
        return out
    wv, bv = list(w.values()), list(b.values())
    out["week_mean"] = mean(wv)
    missing = []
    if len(w) < MIN_WEEK_DAYS:
        missing.append(f"{MIN_WEEK_DAYS - len(w)} more day(s) of {rule['label']} this week (have {len(w)}, need {MIN_WEEK_DAYS})")
    if len(b) < MIN_BASELINE_DAYS:
        missing.append(f"{MIN_BASELINE_DAYS - len(b)} more logged day(s) of {rule['label']} in the three weeks before this one (have {len(b)}, need {MIN_BASELINE_DAYS})")
    if missing:
        out.update(status="insufficient", missing=missing)
        return out
    bm, sd = mean(bv), stdev(bv)
    delta = out["week_mean"] - bm
    med_delta = median(wv) - median(bv)
    out.update(baseline_mean=bm, baseline_sd=sd, delta=delta, median_delta=med_delta,
               standardised=(delta / sd) if sd > 0 else None)
    if abs(delta) < rule["min_delta"] or (sd > 0 and abs(delta) < sd):
        out["status"] = "stable"
    elif delta * med_delta <= 0 or abs(med_delta) < rule["min_delta"]:
        out["status"] = "unstable"   # median does not confirm the mean shift: outlier-driven, do not report as a change
    else:
        out["status"] = "changed"
    return out


def _window_ref(window: ReportingWindow) -> dict:
    return {"week": [window.week_start.isoformat(), window.week_end.isoformat()],
            "baseline": [window.baseline_start.isoformat(), window.baseline_end.isoformat()],
            "timezone": window.tz_name}


def _change_finding(a: dict, window: ReportingWindow) -> dict:
    rule = CHANGE_RULES[a["kind"]]
    d = a["delta"]
    direction = "higher" if d > 0 else "lower"
    u = rule["unit"]
    body = (f"On {a['week_days']} logged days this week your {rule['label']} averaged {a['week_mean']:.1f}{u}, "
            f"{abs(d):.1f}{u} {direction} than the {a['baseline_mean']:.1f}{u} average across the {a['baseline_days']} days "
            f"you logged in the three weeks before. This describes your recorded data; it does not show why it changed.")
    return {
        "id": f"descriptive_summary:{a['kind']}:change", "type": "descriptive_summary",
        "title": f"Your {rule['label']} was {direction} than your recent baseline.", "body": body,
        "evidence": {"source": "observations", "kind": a["kind"], "method": "difference of daily means vs prior-3-week baseline",
                     "n_week_days": a["week_days"], "n_baseline_days": a["baseline_days"],
                     "week_mean": round(a["week_mean"], 2), "baseline_mean": round(a["baseline_mean"], 2),
                     "baseline_sd": round(a["baseline_sd"], 2), "delta": round(d, 2), "windows": _window_ref(window),
                     "gate": f"|mean delta| >= {rule['min_delta']}{u.strip()} and >= baseline day-to-day SD; median delta has the same sign and is also >= {rule['min_delta']}{u.strip()}",
                     "median_delta": round(a["median_delta"], 2)},
        "confidence": None,
        "uncertainty": "No interval is computed for this descriptive comparison; self-reported values are coarse.",
        "limitations": ["Not tested for a relationship with any other variable.", "A single week can differ from baseline by chance."],
    }


def _stable_finding(analyses: list, window: ReportingWindow) -> dict:
    kinds = [CHANGE_RULES[a["kind"]]["label"] for a in analyses]
    return {
        "id": "descriptive_summary:no_meaningful_change", "type": "descriptive_summary",
        "title": "No meaningful change from your recent baseline.",
        "body": (f"Your {', '.join(kinds)} this week stayed within your usual day-to-day range compared with the three weeks before. "
                 "No meaningful change has been established."),
        "evidence": {"source": "observations", "kinds": [a["kind"] for a in analyses], "method": "difference of daily means vs prior-3-week baseline",
                     "n_week_days": {a["kind"]: a["week_days"] for a in analyses},
                     "n_baseline_days": {a["kind"]: a["baseline_days"] for a in analyses}, "windows": _window_ref(window)},
        "confidence": None, "uncertainty": "Absence of a detected change is not proof that nothing changed.",
        "limitations": ["Small weekly samples can hide real differences."],
    }


def _insufficient_finding(analyses: list, window: ReportingWindow) -> dict:
    missing = {a["kind"]: a["missing"] for a in analyses}
    lines = [f"{CHANGE_RULES[k]['label']}: " + "; ".join(v) for k, v in missing.items()]
    return {
        "id": "insufficient_evidence:comparison", "type": "insufficient_evidence",
        "title": "Not enough history to compare yet.",
        "body": "A comparison with your baseline can't be supported yet. Missing: " + " | ".join(lines) + ".",
        "evidence": {"source": "observations", "missing": missing, "windows": _window_ref(window)},
        "confidence": None, "uncertainty": None, "limitations": [],
    }


def _experiment(top: dict) -> dict:
    rule = CHANGE_RULES[top["kind"]]
    label = rule["label"]
    return {
        "question": f"Is the recent difference in your {label} a one-week blip or does it continue?",
        "observed_variable": f"{label} (log as usual; no change to your routine is needed)",
        "period": "the next 7 days",
        "outcome_measured": f"daily {label}, compared with the same baseline",
        "confounders": ["workload and schedule changes", "caffeine and alcohol", "weekday pattern", "only about 7 data points"],
        "supports_if": f"your {label} stays on the same side of the baseline on most logged days",
        "weakens_if": f"your {label} returns to within its usual range",
        "scope_note": "Observation only. This is not a medical test and implies no cause.",
    }


def _experiment_text(e: dict) -> str:
    return (f"For {e['period']}: keep logging as usual. Question: {e['question']} "
            f"This would be supported if {e['supports_if']}, and weakened if {e['weakens_if']}.")


# --------------------------------------------------------------------------- #
# Research-engine adapter
# --------------------------------------------------------------------------- #
def engine_state(run: Optional[dict], *, now: datetime, newest_ingested_at: Optional[datetime] = None,
                 current_model_version: Optional[str] = None) -> dict:
    """Describe what the engine has actually done. Mere presence of a run is never 'analysed'.

    ``run``: {id, status, created_at, model_version, summary, failure_category} or None.
    ``newest_ingested_at`` is INGESTION time (max recorded_at): late-arriving rows make a run stale.
    """
    if run is None:
        return {"state": "not_run", "run_id": None, "stale_reasons": []}
    base = {"run_id": run.get("id"), "run_at": as_utc(run["created_at"]).isoformat() if run.get("created_at") else None,
            "model_version": run.get("model_version"), "engine": (run.get("summary") or {}).get("engine"),
            "window_days": (run.get("summary") or {}).get("window_days"), "stale_reasons": []}
    status = run.get("status")
    if status == "interrupted":
        return {**base, "state": "interrupted"}
    if status == "running":
        started = as_utc(run["created_at"])
        return {**base, "state": "interrupted" if as_utc(now) - started > RUN_STALE_AFTER else "running"}
    if status == "failed":
        return {**base, "state": "failed", "failure_category": run.get("failure_category") or "unknown"}
    if status != "completed":
        return {**base, "state": "failed", "failure_category": f"unexpected_status:{status}"}
    reasons = []
    if current_model_version and run.get("model_version") != current_model_version:
        reasons.append("model_version_changed")
    if as_utc(now) - as_utc(run["created_at"]) > ENGINE_TTL:
        reasons.append("older_than_freshness_window")
    if newest_ingested_at is not None and as_utc(newest_ingested_at) > as_utc(run["created_at"]):
        reasons.append("new_observations_since_run")
    return {**base, "state": "stale" if reasons else "current", "stale_reasons": reasons}


def _tier_level(code) -> Optional[int]:
    try:
        return int(str(code).split("-")[-1])
    except (TypeError, ValueError):
        return None


def adapt_engine_findings(candidates: Optional[list], *, user_id, state: dict, current_model_version: Optional[str],
                          max_items: int = MAX_ENGINE_FINDINGS) -> tuple:
    """Convert eligible engine hypotheses into report findings. Returns ``(findings, excluded_counts)``.

    Fails closed: a candidate without a matching ``user_id`` is excluded as unauthorised.
    """
    excluded = defaultdict(int)
    if state["state"] not in ("current", "stale"):
        if candidates:
            excluded["engine_state_" + state["state"]] += len(candidates)
        return [], dict(excluded)
    eligible = []
    for c in candidates or []:
        if c.get("user_id") != user_id:
            excluded["unauthorised"] += 1
        elif c.get("status") not in ELIGIBLE_HYPOTHESIS_STATUS:
            excluded["status_not_reportable"] += 1
        elif current_model_version and c.get("model_version") != current_model_version:
            excluded["model_version_mismatch"] += 1
        elif c.get("echo_of"):
            excluded["echo_of_stronger_candidate"] += 1
        else:
            lvl = _tier_level(c.get("evidence_tier"))
            if lvl not in TIER_TYPE:
                excluded["below_reporting_tier"] += 1
            else:
                eligible.append((lvl, c))
    eligible.sort(key=lambda t: (-t[0], t[1].get("q_value") if t[1].get("q_value") is not None else 1.0,
                                 -(t[1].get("n_pairs") or 0), str(t[1].get("hypothesis_id"))))
    findings = []
    for lvl, c in eligible[:max_items]:
        ftype, ex, out = TIER_TYPE[lvl], _pretty(c.get("exposure")), _pretty(c.get("outcome"))
        lag = f" at a {c['lag']}-day lag" if c.get("lag") else ""
        n = c.get("n_pairs")
        label = c.get("evidence_label") or ""
        if ftype == "hypothesis":
            title, body = f"A weak signal between {ex} and {out} is worth watching.", (
                f"A faint link between {ex} and {out}{lag} appeared in your data. At this level it is still consistent with chance "
                "after accounting for the many comparisons made, so treat it as a question, not a finding.")
        elif ftype == "candidate_association":
            title, body = f"{ex.capitalize()} and {out} have moved together in your records.", (
                f"Across {n if n else 'your'} paired days, {ex} and {out}{lag} moved together ({c.get('evidence_tier')}: {label}). "
                "This is an observational association; it does not show that one causes the other.")
        else:
            title, body = f"A pattern between {ex} and {out} held up on new days.", (
                f"A model fitted earlier predicted {out} from {ex}{lag} on days it had not seen ({c.get('evidence_tier')}: {label}). "
                "This supports a pattern in your own data. It is not a medical finding and does not establish cause.")
        findings.append({
            "id": f"{ftype}:{c.get('hypothesis_id')}", "type": ftype, "title": title, "body": body,
            "evidence": {"source": "research_engine", "hypothesis_id": c.get("hypothesis_id"), "evidence_tier": c.get("evidence_tier"),
                         "n_pairs": n, "q_value": c.get("q_value"), "effect_estimate": c.get("effect_estimate"),
                         "run_id": state.get("run_id"), "model_version": c.get("model_version"), "last_tested_at": c.get("last_tested_at")},
            "confidence": c.get("confidence"),
            "uncertainty": "See evidence tier; observational personal data.",
            "limitations": (["Based on an earlier analysis run; newer data has not been analysed yet."] if state["state"] == "stale" else [])
                           + ["Unmeasured factors may explain the pattern."],
        })
    return findings, dict(excluded)


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #
def _fingerprint(b: Bucketed) -> str:
    rows = [(o.kind, o.event_utc.isoformat(), o.value_numeric, o.value_text) for o in b.week + b.baseline]
    return hashlib.sha256(json.dumps(sorted(rows, key=repr), default=str).encode()).hexdigest()[:16]


def build_weekly_report(records: Iterable, *, user_id, tz_name: Optional[str], now: datetime, profile: Optional[dict] = None,
                        engine_run: Optional[dict] = None, engine_candidates: Optional[list] = None,
                        newest_ingested_at: Optional[datetime] = None, current_model_version: Optional[str] = None) -> dict:
    t0 = time.perf_counter()
    window = weekly_window(now, tz_name)
    b = bucket_observations(records, window, now)
    t1 = time.perf_counter()

    week_days = sorted({o.day for o in b.week})
    coverage = {"days": len(week_days), "observations": len(b.week), "baseline_observations": len(b.baseline),
                "baseline_days": len({o.day for o in b.baseline}), "legacy_event_time_observations": b.legacy_event_time,
                "quarantined": b.quarantined, "duplicates_dropped": b.duplicates_dropped,
                "outside_window": b.outside_window}

    warnings = []
    if window.tz_fallback:
        warnings.append({"code": "timezone_fallback_utc", "message": "Your timezone is not set or not recognised, so days were split at UTC midnight."})
    if b.legacy_event_time:
        warnings.append({"code": "legacy_event_time", "message": f"{b.legacy_event_time} observation(s) have no recorded event time; the time they were saved was used instead."})
    if b.missing_event_time:
        warnings.append({"code": "missing_event_time", "message": f"{b.missing_event_time} observation(s) without any usable time were excluded."})
    if b.future_dated:
        warnings.append({"code": "future_dated", "message": f"{b.future_dated} observation(s) dated in the future were excluded."})
    if b.duplicates_dropped:
        warnings.append({"code": "duplicates_dropped", "message": f"{b.duplicates_dropped} exact duplicate observation(s) were counted once."})
    if 0 < len(week_days) < MIN_WEEK_DAYS:
        warnings.append({"code": "sparse_week", "message": f"Only {len(week_days)} day(s) were logged this week."})

    state = engine_state(engine_run, now=now, newest_ingested_at=newest_ingested_at, current_model_version=current_model_version)
    t2 = time.perf_counter()

    findings, analyses = [], {}
    if b.week:
        for kind in CHANGE_RULES:
            analyses[kind] = analyse_kind(b.week, b.baseline, kind)
        changed = [a for a in analyses.values() if a["status"] == "changed"]
        changed.sort(key=lambda a: -abs(a["standardised"]) if a["standardised"] is not None else -abs(a["delta"] / CHANGE_RULES[a["kind"]]["min_delta"]))
        findings += [_change_finding(a, window) for a in changed[:MAX_DESCRIPTIVE_FINDINGS]]
        for a in analyses.values():
            if a["status"] == "unstable":
                warnings.append({"code": "outlier_sensitive", "message": f"The apparent change in {CHANGE_RULES[a['kind']]['label']} depends on a few values and was not reported."})
        stable = [a for a in analyses.values() if a["status"] == "stable"]
        insufficient = [a for a in analyses.values() if a["status"] == "insufficient"]
        if not changed and stable:
            findings.append(_stable_finding(stable, window))
        if insufficient:
            findings.append(_insufficient_finding(insufficient, window))

    engine_findings, excluded = adapt_engine_findings(engine_candidates, user_id=user_id, state=state, current_model_version=current_model_version)
    findings += engine_findings
    if state["state"] == "current" and not engine_findings:
        state = {**state, "state": "no_eligible_findings"}
    if state["state"] == "failed":
        warnings.append({"code": "engine_failed", "message": "The most recent research-engine run failed; no engine results are shown."})
    elif state["state"] == "stale":
        warnings.append({"code": "engine_stale", "message": "Research-engine results come from an earlier run (" + ", ".join(state["stale_reasons"]) + ")."})
    t3 = time.perf_counter()

    changed_present = any(f["id"].endswith(":change") for f in findings)
    top = max((a for a in analyses.values() if a["status"] == "changed"), key=lambda a: abs(a["delta"] / CHANGE_RULES[a["kind"]]["min_delta"]), default=None) if changed_present else None
    experiment = _experiment(top) if top else None

    if not b.week:
        status, report_state = "not_ready", "no_data"
    else:
        status = "ready"
        substantive = [f for f in findings if f["type"] != "insufficient_evidence"]
        report_state = "insufficient_data" if not substantive else ("completed_with_warnings" if warnings else "completed")
    if report_state == "insufficient_data" and warnings:
        pass  # warnings remain visible alongside the insufficiency statement

    report_id = "wk-" + hashlib.sha256(json.dumps(
        [SCHEMA_VERSION, ALGORITHM_VERSION, str(user_id), _window_ref(window), _fingerprint(b), state.get("run_id")], default=str).encode()).hexdigest()[:20]

    report = {
        "schema_version": SCHEMA_VERSION, "algorithm_version": ALGORITHM_VERSION, "report_id": report_id,
        "status": status, "report_state": report_state,
        "title": "Your week with NexGene", "subtitle": "A plain read of the signal so far.",
        "generated_at": as_utc(now).isoformat(), "generation": {"method": "deterministic", "language_model_used": False},
        "period": {"timezone": window.tz_name, "week_start": window.week_start.isoformat(), "week_end": window.week_end.isoformat(),
                   "baseline_start": window.baseline_start.isoformat(), "baseline_end": window.baseline_end.isoformat()},
        "profile": profile or {},
        "coverage": coverage, "data_quality_warnings": warnings,
        "findings": findings,
        "sections": [{"kind": f["type"], "title": f["title"], "body": f["body"], "finding_id": f["id"]} for f in findings],
        "experiment": _experiment_text(experiment) if experiment else None, "experiment_detail": experiment,
        "engine": {**state, "excluded": excluded},
        "limitations": STANDING_LIMITATIONS, "disclaimer": DISCLAIMER,
        "timings_ms": {"bucketing": round((t1 - t0) * 1000, 3), "engine_state": round((t2 - t1) * 1000, 3),
                       "analysis": round((t3 - t2) * 1000, 3), "total": round((time.perf_counter() - t0) * 1000, 3)},
    }
    if status == "not_ready":
        report["message"] = "No observations with an event time in the last 7 days yet. Log a check-in and the first report will take shape."
    return report
