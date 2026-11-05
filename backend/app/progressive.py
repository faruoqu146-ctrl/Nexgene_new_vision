"""Progressive intelligence: honest, deterministic feedback from the very first check-in.

The previous experience gated *everything* behind history: until a user had weeks of data the API
returned a generic "not enough data" card and nothing that reflected what they had just recorded.
This module separates what can be said at each evidence level, so a new user gets real feedback
while no scientific threshold is lowered.

  Level 1  Immediate observations   >= 1 recorded observation. Recorded values, daily interpretation,
                                    what is missing. Never claims a trend.
  Level 2  Preliminary patterns     >= 2 days with the same measurement (recurring observations: >= 3).
                                    Descriptive only; sample size and the absence of a confidence
                                    interval are disclosed on every item.
  Level 3  Exploratory associations Produced ONLY by the research engine, with its own minimum paired
                                    observations (``EngineConfig.min_pairs``) and multiple-testing control.
                                    This module never computes an association; it reports engine results
                                    that already passed the engine's gates, and how far each pair is from
                                    being testable.
  Level 4  Personal baseline        The existing recent-7-days vs prior-21-days comparison, with the
                                    existing coverage gates (``weekly.MIN_WEEK_DAYS`` /
                                    ``weekly.MIN_BASELINE_DAYS``) re-used, not copied or relaxed.

Everything is a pure function of (records, timezone, now[, engine results]). Day boundaries are the
user's local calendar days and observations are placed by EVENT time (see ``temporal``), so the
Today snapshot, signals, patterns and weekly report can never disagree about which day something
belongs to. No language model is involved. Output never contains a causal or diagnostic claim.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Iterable, Optional

try:
    from . import weekly as W
    from .checkin import EVENING_CORE, EVENING_OPTIONAL, MORNING_CORE, MORNING_OPTIONAL, SKIPPED
    from .research.config import BEHAVIOR_EXPOSURES, DEFAULT_CONFIG, SCALE_0_10, STATE_OUTCOMES
    from .temporal import ReportingWindow, as_utc, bucket_observations, local_day, resolve_tz, weekly_window
except ImportError:  # pragma: no cover - executed as a script from backend/app
    import weekly as W
    from checkin import EVENING_CORE, EVENING_OPTIONAL, MORNING_CORE, MORNING_OPTIONAL, SKIPPED
    from research.config import BEHAVIOR_EXPOSURES, DEFAULT_CONFIG, SCALE_0_10, STATE_OUTCOMES
    from temporal import ReportingWindow, as_utc, bucket_observations, local_day, resolve_tz, weekly_window

SCHEMA_VERSION = "nexgene.progressive/1"
ALGORITHM_VERSION = "progressive-descriptive/1"
LAYOUT_VERSION = "weekly-layout/1"

# Level 2 is descriptive, so its gates are about *describing* what was recorded, not inferring.
PRELIM_MIN_DAYS = 2        # two distinct local days are needed to describe a change between days
RECURRING_MIN_DAYS = 3     # a recurring observation needs >= 3 recorded days and >= 2 occurrences
HISTORY_DAYS = 365         # how far back the progressive view looks
MAX_SIGNALS = 4
MAX_NEXT = 4

LEVELS = {
    1: ("observations", "Immediate observations"),
    2: ("preliminary_patterns", "Preliminary patterns"),
    3: ("associations", "Exploratory associations"),
    4: ("baseline", "Personal baseline"),
}

LABEL_OVERRIDES = {"morning_context": "morning note", "activity_level": "activity", "diet_quality": "eating",
                   "sleep_duration": "sleep", "sleep_quality": "sleep quality"}
ORDER = list(MORNING_CORE) + list(MORNING_OPTIONAL) + list(EVENING_CORE) + list(EVENING_OPTIONAL)
STANDING_LIMITATIONS = list(W.STANDING_LIMITATIONS) + [
    "Early observations describe what you recorded; they are not a trend, a diagnosis or medical advice.",
]
DISCLAIMER = W.DISCLAIMER


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def _label(kind: str) -> str:
    return LABEL_OVERRIDES.get(kind) or str(kind).replace("_", " ")


def _num(v: float) -> str:
    s = f"{v:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _fmt(kind: str, v) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v.replace("_", " ")
    if kind == "sleep_duration":
        return f"{_num(v)} h"
    if kind in SCALE_0_10:
        return f"{_num(v)}/10"
    return _num(v)


def _scale_position(kind: str, v) -> Optional[str]:
    """Position on the 0-10 scale the person used. Neutral wording: it does not say whether that is good."""
    if kind not in SCALE_0_10 or not isinstance(v, (int, float)):
        return None
    if v <= 3:
        return "toward the low end of the 0-10 scale"
    if v >= 7:
        return "toward the high end of the 0-10 scale"
    return "around the middle of the 0-10 scale"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# --------------------------------------------------------------------------- #
# Preparation
# --------------------------------------------------------------------------- #
class _Prepared:
    """Observations bucketed once, by event time and local day, with skips separated out."""

    def __init__(self, records: Iterable, tz_name: Optional[str], now: datetime):
        tz, fallback = resolve_tz(tz_name)
        self.tz_name = tz_name or "UTC"
        self.tz_fallback = fallback
        self.now = as_utc(now)
        self.today: date = local_day(self.now, tz)
        window = ReportingWindow(self.tz_name, fallback, self.today - timedelta(days=6), self.today,
                                 self.today - timedelta(days=HISTORY_DAYS), self.today - timedelta(days=7))
        b = bucket_observations(records, window, self.now)
        merged = sorted(b.baseline + b.week, key=lambda o: (o.event_utc, o.kind))
        self.skipped = [o for o in merged if o.value_text == SKIPPED]
        self.items = [o for o in merged if o.value_text != SKIPPED]
        self.bucketed = b
        self.weekly_window = weekly_window(self.now, tz_name)
        # daily numeric means and per-day text values, by kind
        nums = defaultdict(lambda: defaultdict(list))
        texts = defaultdict(lambda: defaultdict(list))
        for o in self.items:
            if o.value_numeric is not None:
                nums[o.kind][o.day].append(o.value_numeric)
            elif o.value_text is not None:
                texts[o.kind][o.day].append(o.value_text)
        self.daily = {k: {d: mean(v) for d, v in days.items()} for k, days in nums.items()}
        self.text_days = {k: dict(days) for k, days in texts.items()}
        self.all_days = sorted({o.day for o in self.items})

    def in_window(self, start: date, end: date) -> list:
        return [o for o in self.items if start <= o.day <= end]


# --------------------------------------------------------------------------- #
# Level 1: today's snapshot
# --------------------------------------------------------------------------- #
def _period_state(by_kind: dict, core: tuple, optional: tuple) -> dict:
    present_core = [k for k in core if k in by_kind]
    missing_core = [k for k in core if k not in by_kind]
    present_optional = [k for k in optional if k in by_kind]
    if not missing_core:
        status = "complete"
    elif present_core or present_optional:
        status = "partial"
    else:
        status = "missing"
    return {"status": status, "recorded": present_core + present_optional,
            "missing_core": missing_core, "missing_optional": [k for k in optional if k not in by_kind]}


def _today_snapshot(p: _Prepared) -> dict:
    todays = [o for o in p.items if o.day == p.today]
    by_kind = defaultdict(list)
    for o in todays:
        by_kind[o.kind].append(o)
    values = []
    for kind in sorted(by_kind, key=lambda k: (ORDER.index(k) if k in ORDER else len(ORDER), k)):
        obs = sorted(by_kind[kind], key=lambda o: o.event_utc)
        last = obs[-1]
        value = last.value_numeric if last.value_numeric is not None else last.value_text
        entry = {"kind": kind, "label": _label(kind), "value": value, "display": _fmt(kind, value),
                 "unit_scale": "0-10" if kind in SCALE_0_10 else None,
                 "n_readings": len(obs), "observed_at": last.event_utc.isoformat(), "event_time_basis": last.basis}
        if len(obs) > 1 and last.value_numeric is not None:
            entry["day_mean"] = round(mean(o.value_numeric for o in obs if o.value_numeric is not None), 2)
            entry["note"] = f"{len(obs)} readings today; the latest is shown."
        values.append(entry)
    morning = _period_state(by_kind, MORNING_CORE, MORNING_OPTIONAL)
    evening = _period_state(by_kind, EVENING_CORE, EVENING_OPTIONAL)
    complete = sum(1 for s in (morning, evening) if s["status"] == "complete")
    state = "empty" if not values else ("complete" if complete == 2 else "partial")
    skipped_today = sorted({o.kind for o in p.skipped if o.day == p.today})
    return {"date": p.today.isoformat(), "state": state, "check_ins_complete": complete, "check_ins_expected": 2,
            "values": values, "periods": {"morning": morning, "evening": evening},
            "skipped": [{"kind": k, "label": _label(k)} for k in skipped_today],
            "repeated_readings": sorted(e["kind"] for e in values if e["n_readings"] > 1)}


def _daily_interpretation(snapshot: dict) -> list:
    """Plain statements about today's recorded values. No trend, no norm, no cause."""
    out = []
    vals = {v["kind"]: v for v in snapshot["values"]}

    def say(sid, text, kinds):
        out.append({"id": sid, "type": "descriptive_summary", "text": text, "kinds": kinds})

    for period in ("morning", "evening"):
        st = snapshot["periods"][period]
        core = MORNING_CORE if period == "morning" else EVENING_CORE
        got = [k for k in core if k in vals]
        if got:
            parts = ", ".join(f"{vals[k]['label']} {vals[k]['display']}" for k in got)
            lead = f"{period.capitalize()} check-in recorded: {parts}."
            pos = [f"{vals[k]['label']} is {_scale_position(k, vals[k]['value'])}" for k in got
                   if k in SCALE_0_10 and _scale_position(k, vals[k]['value'])]
            if pos:
                joined = "; ".join(pos[:3])
                lead += " " + joined[0].upper() + joined[1:] + "."
            say(f"today:{period}:recorded", lead, got)
        if st["status"] == "partial" and st["missing_core"]:
            say(f"today:{period}:incomplete",
                f"The {period} check-in is incomplete: {', '.join(_label(k) for k in st['missing_core'])} not recorded yet.",
                st["missing_core"])
    if "sleep_duration" in vals and "sleep_quality" in vals:
        say("today:sleep_pair",
            f"You logged {vals['sleep_duration']['display']} of sleep and rated it {vals['sleep_quality']['display']}. "
            "These are today's values; a single day cannot show how they relate.", ["sleep_duration", "sleep_quality"])
    repeated = [vals[k]["label"] for k in snapshot["repeated_readings"] if k in vals]
    if repeated:
        say("today:repeated", f"More than one reading was saved today for {', '.join(repeated)}; the latest is shown and the day is averaged in summaries.",
            snapshot["repeated_readings"])
    if snapshot["state"] == "empty":
        say("today:empty", "Nothing has been recorded today yet. One short check-in is enough to start.", [])
    return out


# --------------------------------------------------------------------------- #
# Level 2: preliminary, descriptive patterns
# --------------------------------------------------------------------------- #
def _limits(n_days: int) -> list:
    return [f"Based on {_plural(n_days, 'recorded day')}; too few to call a trend.",
            "Descriptive only: no significance test or confidence interval is computed.",
            "Self-reported values are coarse and subjective."]


def _preliminary(p: _Prepared, since: Optional[date] = None) -> list:
    items = []
    for kind in sorted(p.daily, key=lambda k: (ORDER.index(k) if k in ORDER else len(ORDER), k)):
        days = sorted(d for d in p.daily[kind] if since is None or d >= since)
        if len(days) < PRELIM_MIN_DAYS:
            continue
        vals = [p.daily[kind][d] for d in days]
        latest, prev = vals[-1], vals[-2]
        delta = latest - prev
        rule = W.CHANGE_RULES.get(kind)
        threshold = rule["min_delta"] if rule else None
        if threshold is not None and abs(delta) < threshold:
            direction = "similar"
        elif delta > 0:
            direction = "higher"
        elif delta < 0:
            direction = "lower"
        else:
            direction = "similar"
        label = _label(kind)
        if direction == "similar":
            body = (f"Your {label} on {days[-1].isoformat()} ({_fmt(kind, latest)}) was similar to {days[-2].isoformat()} "
                    f"({_fmt(kind, prev)}).")
        else:
            body = (f"Your {label} on {days[-1].isoformat()} was {_fmt(kind, latest)}, "
                    f"{_fmt(kind, abs(delta))} {direction} than on {days[-2].isoformat()} ({_fmt(kind, prev)}).")
        if len(days) >= RECURRING_MIN_DAYS:
            body += f" Across {len(days)} recorded days it ranged from {_fmt(kind, min(vals))} to {_fmt(kind, max(vals))} (average {_fmt(kind, mean(vals))})."
        body += " This describes what you recorded; it is not a trend."
        items.append({
            "id": f"preliminary:{kind}", "type": "descriptive_summary", "kind": kind, "label": label,
            "title": f"{label.capitalize()}: {_fmt(kind, latest)} on your latest recorded day.", "body": body,
            "direction": direction,
            "sample": {"days": len(days), "span_days": (days[-1] - days[0]).days + 1,
                       "observations": sum(1 for o in p.items if o.kind == kind and (since is None or o.day >= since))},
            "stats": {"latest": round(latest, 2), "previous": round(prev, 2), "change_from_previous": round(delta, 2),
                      "mean": round(mean(vals), 2), "min": round(min(vals), 2), "max": round(max(vals), 2),
                      "latest_day": days[-1].isoformat(), "previous_day": days[-2].isoformat()},
            "confidence": None, "limitations": _limits(len(days)),
        })
    # recurring categorical observations (never numeric, never 'none')
    for kind, by_day in sorted(p.text_days.items()):
        days = sorted(d for d in by_day if since is None or d >= since)
        if len(days) < RECURRING_MIN_DAYS:
            continue
        counts = defaultdict(int)
        for d in days:
            for v in set(by_day[d]):
                if v not in ("none", SKIPPED):
                    counts[v] += 1
        for value, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            if n >= 2:
                label = _label(kind)
                items.append({
                    "id": f"recurring:{kind}:{value}", "type": "descriptive_summary", "kind": kind, "label": label,
                    "title": f"“{value.replace('_', ' ')}” appeared on {n} of {len(days)} recorded days.",
                    "body": f"For {label}, you chose “{value.replace('_', ' ')}” on {n} of {_plural(len(days), 'recorded day')}. "
                            "This counts what you chose; it does not say why.",
                    "direction": None, "sample": {"days": len(days), "span_days": (days[-1] - days[0]).days + 1, "observations": n},
                    "stats": {"occurrences": n, "days": len(days)}, "confidence": None, "limitations": _limits(len(days)),
                })
                break  # most frequent value only
    return items


# --------------------------------------------------------------------------- #
# Level 3: associations (engine-produced only) and how close each pair is to testable
# --------------------------------------------------------------------------- #
def _pair_progress(p: _Prepared, limit: int = 3) -> list:
    need, support = DEFAULT_CONFIG.min_pairs, DEFAULT_CONFIG.min_pairs_support
    rows = []
    for exp in sorted(BEHAVIOR_EXPOSURES):
        for out in sorted(STATE_OUTCOMES):
            if exp == out or exp not in p.daily or out not in p.daily:
                continue
            n = len(set(p.daily[exp]) & set(p.daily[out]))
            if n:
                rows.append({"exposure": exp, "outcome": out, "paired_days": n, "needed_to_test": need,
                             "needed_for_robust_association": support,
                             "remaining_to_test": max(0, need - n),
                             "label": f"{_label(exp)} and {_label(out)}"})
    rows.sort(key=lambda r: (-r["paired_days"], r["exposure"], r["outcome"]))
    return rows[:limit]


def _associations(p: _Prepared, *, user_id, engine_run, engine_candidates, newest_ingested_at, current_model_version) -> dict:
    state = W.engine_state(engine_run, now=p.now, newest_ingested_at=newest_ingested_at,
                           current_model_version=current_model_version)
    findings, excluded = W.adapt_engine_findings(engine_candidates, user_id=user_id, state=state,
                                                 current_model_version=current_model_version)
    progress = _pair_progress(p)
    need, support = DEFAULT_CONFIG.min_pairs, DEFAULT_CONFIG.min_pairs_support
    if findings:
        status = "available"
    elif progress:
        status = "collecting"
    else:
        status = "locked"
    return {
        "status": status, "items": findings, "pair_progress": progress,
        "requires": (f"Two measurements need at least {need} days recorded together before the research engine will test them, "
                     f"and {support} before a result can be called a robust association. Results also pass multiple-testing control."),
        "engine": {**state, "excluded": excluded},
        "limitations": ["Associations are observational and never show that one thing causes another.",
                        "Only the research engine produces associations; nothing is estimated on this screen."],
    }


# --------------------------------------------------------------------------- #
# Level 4: personal baseline (existing methodology, existing gates)
# --------------------------------------------------------------------------- #
def _baseline(p: _Prepared) -> dict:
    wk = p.weekly_window
    week_obs = p.in_window(wk.week_start, wk.week_end)
    base_obs = p.in_window(wk.baseline_start, wk.baseline_end)
    analyses = {k: W.analyse_kind(week_obs, base_obs, k) for k in W.CHANGE_RULES}
    comparisons, progress = [], []
    for kind, a in analyses.items():
        if a["status"] == "no_week_data":
            if any(o.kind == kind for o in base_obs):
                progress.append({"kind": kind, "label": _label(kind), "week_days": 0, "need_week_days": W.MIN_WEEK_DAYS,
                                 "baseline_days": a["baseline_days"], "need_baseline_days": W.MIN_BASELINE_DAYS})
            continue
        if a["status"] == "insufficient":
            progress.append({"kind": kind, "label": _label(kind), "week_days": a["week_days"], "need_week_days": W.MIN_WEEK_DAYS,
                             "baseline_days": a["baseline_days"], "need_baseline_days": W.MIN_BASELINE_DAYS,
                             "missing": a["missing"]})
            continue
        entry = {"kind": kind, "label": _label(kind), "status": a["status"], "n_week_days": a["week_days"],
                 "n_baseline_days": a["baseline_days"], "week_mean": round(a["week_mean"], 2),
                 "baseline_mean": round(a["baseline_mean"], 2), "delta": round(a["delta"], 2),
                 "limitations": ["A difference between two periods does not show why it happened.",
                                 "A single week can differ from baseline by chance."]}
        if a["status"] == "changed":
            f = W._change_finding(a, wk)
            entry.update(title=f["title"], body=f["body"], evidence=f["evidence"])
        elif a["status"] == "stable":
            entry.update(title=f"{_label(kind).capitalize()} stayed within your usual range.",
                         body=(f"Across {a['week_days']} logged days this week your {_label(kind)} averaged {_fmt(kind, a['week_mean'])} "
                               f"against {_fmt(kind, a['baseline_mean'])} over the {a['baseline_days']} days logged in the three weeks before. "
                               "No meaningful change has been established."))
        else:  # unstable
            entry.update(title=f"{_label(kind).capitalize()}: the apparent change depends on a few values.",
                         body="The average moved but the median did not confirm it, so no change is reported.")
        comparisons.append(entry)
    return {
        "status": "available" if comparisons else "locked", "comparisons": comparisons, "progress": progress,
        "comparison_period": {"recent": [wk.week_start.isoformat(), wk.week_end.isoformat()],
                              "baseline": [wk.baseline_start.isoformat(), wk.baseline_end.isoformat()], "timezone": wk.tz_name},
        "requires": (f"At least {W.MIN_WEEK_DAYS} logged days of a measurement in the last 7 days and {W.MIN_BASELINE_DAYS} logged days "
                     "of it in the 21 days before that."),
        "limitations": ["Compares the last 7 days with the 21 days before them; the recent week is never part of its own baseline."],
    }


# --------------------------------------------------------------------------- #
# Signals and suggested next observations
# --------------------------------------------------------------------------- #
def _next_observations(p: _Prepared, today: dict, baseline: dict, assoc: dict) -> list:
    out = []
    for period in ("morning", "evening"):
        st = today["periods"][period]
        if st["status"] != "complete":
            miss = st["missing_core"]
            out.append({"id": f"next:{period}", "priority": 1, "action": "check_in", "period": period,
                        "text": (f"Complete today's {period} check-in" + (f" ({', '.join(_label(k) for k in miss)})." if miss else "."))})
    grouped = defaultdict(list)
    for item in baseline["progress"]:
        have, need = item["week_days"], item["need_week_days"]
        if 0 < have < need:
            grouped[need - have].append(item["label"])
    for remaining, labels in sorted(grouped.items()):
        listed = ", ".join(labels[:3]) + (f" and {len(labels) - 3} more" if len(labels) > 3 else "")
        out.append({"id": f"next:week:{remaining}", "priority": 2, "action": "check_in",
                    "text": f"Log {listed} on {_plural(remaining, 'more day')} this week to enable a comparison with your baseline."})
    kinds_total = {k: len(d) for k, d in p.daily.items()}
    if kinds_total and not baseline["comparisons"] and not grouped:
        best = max(kinds_total, key=lambda k: (kinds_total[k], k))
        if kinds_total[best] < W.MIN_WEEK_DAYS + W.MIN_BASELINE_DAYS:
            out.append({"id": "next:baseline", "priority": 3, "action": "check_in",
                        "text": (f"A personal baseline needs {W.MIN_WEEK_DAYS} logged days in the last 7 and {W.MIN_BASELINE_DAYS} in the 21 days "
                                 f"before. Your most-logged measurement ({_label(best)}) has {_plural(kinds_total[best], 'day')} so far.")})
    for pr in assoc["pair_progress"][:1]:
        if pr["remaining_to_test"] > 0:
            out.append({"id": "next:pairs", "priority": 4, "action": "check_in",
                        "text": (f"Keep logging {pr['label']} together: {pr['paired_days']} of {pr['needed_to_test']} paired days so far. "
                                 "Until then no association can be tested.")})
    out.sort(key=lambda o: (o["priority"], o["id"]))
    return out[:MAX_NEXT]


def _signals(p: _Prepared, today: dict, interp: list, prelim: list, baseline: dict, assoc: dict, total_days: int) -> dict:
    if not p.items:
        return {"status": "starting", "signals": [{
            "type": "welcome", "level": 0, "title": "Let's start with one small signal.",
            "body": "A morning or evening check-in gives NexGene something to show you straight away.", "action": "check_in"}]}
    sigs = []
    if today["values"]:
        first = interp[0]["text"] if interp else "Today's check-in was recorded."
        sigs.append({"type": "observation", "level": 1, "title": "Here is what you recorded today.", "body": first,
                     "action": "check_in" if today["state"] != "complete" else "patterns"})
    else:
        sigs.append({"type": "observation", "level": 1, "title": "Nothing recorded yet today.",
                     "body": f"You have {_plural(total_days, 'day')} of observations so far. A short check-in adds today.", "action": "check_in"})
    for item in prelim[:2]:
        if item["direction"] in ("higher", "lower"):
            sigs.append({"type": "preliminary", "level": 2, "title": item["title"], "body": item["body"], "action": "patterns",
                         "evidence": {"days": item["sample"]["days"]}})
            break
    changed = [c for c in baseline["comparisons"] if c["status"] == "changed"]
    if changed:
        sigs.append({"type": "baseline", "level": 4, "title": changed[0]["title"], "body": changed[0]["body"], "action": "report",
                     "evidence": {"n_week_days": changed[0]["n_week_days"], "n_baseline_days": changed[0]["n_baseline_days"]}})
    for f in assoc["items"][:1]:
        sigs.append({"type": "association", "level": 3, "title": f["title"], "body": f["body"], "action": "research",
                     "evidence": {"evidence_tier": f["evidence"].get("evidence_tier"), "n_pairs": f["evidence"].get("n_pairs")}})
    if total_days < 7 and len(sigs) < MAX_SIGNALS:
        sigs.append({"type": "milestone", "level": 1, "title": "Your record is just beginning.",
                     "body": (f"{_plural(total_days, 'day')} recorded. Patterns across days need at least {PRELIM_MIN_DAYS}; "
                              f"a personal baseline needs several weeks."), "action": "check_in"})
    return {"status": "active", "signals": sigs[:MAX_SIGNALS]}


# --------------------------------------------------------------------------- #
# Public builders
# --------------------------------------------------------------------------- #
def build_progressive(records: Iterable, *, user_id, tz_name: Optional[str], now: datetime, engine_run: Optional[dict] = None,
                      engine_candidates: Optional[list] = None, newest_ingested_at: Optional[datetime] = None,
                      current_model_version: Optional[str] = None, _prepared: Optional[_Prepared] = None) -> dict:
    p = _prepared or _Prepared(list(records), tz_name, now)
    today = _today_snapshot(p)
    interp = _daily_interpretation(today)
    prelim = _preliminary(p)
    assoc = _associations(p, user_id=user_id, engine_run=engine_run, engine_candidates=engine_candidates,
                          newest_ingested_at=newest_ingested_at, current_model_version=current_model_version)
    base = _baseline(p)
    total_days = len(p.all_days)
    level_status = {
        1: "available" if p.items else "locked",
        2: "available" if prelim else "locked",
        3: assoc["status"],
        4: base["status"],
    }
    available = [lv for lv, st in level_status.items() if st == "available"]
    b = p.bucketed
    warnings = []
    if p.tz_fallback:
        warnings.append({"code": "timezone_fallback_utc", "message": "Your timezone is not set or not recognised, so days were split at UTC midnight."})
    if b.legacy_event_time:
        warnings.append({"code": "legacy_event_time", "message": f"{b.legacy_event_time} observation(s) have no recorded event time; the time they were saved was used instead."})
    if b.duplicates_dropped:
        warnings.append({"code": "duplicates_dropped", "message": f"{b.duplicates_dropped} exact duplicate observation(s) were counted once."})
    if b.future_dated:
        warnings.append({"code": "future_dated", "message": f"{b.future_dated} observation(s) dated in the future were excluded."})
    if b.missing_event_time:
        warnings.append({"code": "missing_event_time", "message": f"{b.missing_event_time} observation(s) without any usable time were excluded."})
    coverage = {
        "total_days": total_days, "total_observations": len(p.items), "days_last_7": len({o.day for o in p.items if o.day >= p.today - timedelta(days=6)}),
        "first_day": p.all_days[0].isoformat() if p.all_days else None, "last_day": p.all_days[-1].isoformat() if p.all_days else None,
        "days_by_kind": {k: len(d) for k, d in sorted(p.daily.items())},
        "skipped_answers": len(p.skipped), "duplicates_dropped": b.duplicates_dropped,
        "legacy_event_time_observations": b.legacy_event_time, "quarantined": b.quarantined,
    }
    return {
        "schema_version": SCHEMA_VERSION, "algorithm_version": ALGORITHM_VERSION, "generated_at": p.now.isoformat(),
        "timezone": p.tz_name, "generation": {"method": "deterministic", "language_model_used": False},
        "today": {**today, "interpretation": interp},
        "levels": {
            "observations": {"level": 1, "label": LEVELS[1][1], "status": level_status[1],
                             "requires": "One recorded observation.", "items": interp},
            "preliminary_patterns": {"level": 2, "label": LEVELS[2][1], "status": level_status[2], "items": prelim,
                                     "requires": f"At least {PRELIM_MIN_DAYS} days with the same measurement ({RECURRING_MIN_DAYS} for recurring observations).",
                                     "progress": {"max_days_for_one_measurement": max([len(d) for d in p.daily.values()] or [0]),
                                                  "needed_days": PRELIM_MIN_DAYS},
                                     "limitations": ["Descriptive only; sample size is shown on every item."]},
            "associations": {"level": 3, "label": LEVELS[3][1], **assoc},
            "baseline": {"level": 4, "label": LEVELS[4][1], **base},
        },
        "highest_level": max(available) if available else 0, "available_levels": available,
        "signals": _signals(p, today, interp, prelim, base, assoc, total_days),
        "next_observations": _next_observations(p, today, base, assoc),
        "coverage": coverage, "data_quality_warnings": warnings,
        "provenance": {"observation_source": "self-reported NexGene check-ins", "event_time_basis":
                       {"observed_at": sum(1 for o in p.items if o.basis == "observed_at"),
                        "recorded_at_legacy": sum(1 for o in p.items if o.basis == "recorded_at_legacy")}},
        "limitations": STANDING_LIMITATIONS, "disclaimer": DISCLAIMER,
    }


def _recorded_observations(p: _Prepared) -> list:
    wk = p.weekly_window
    week = p.in_window(wk.week_start, wk.week_end)
    out = []
    for kind in sorted({o.kind for o in week}, key=lambda k: (ORDER.index(k) if k in ORDER else len(ORDER), k)):
        obs = [o for o in week if o.kind == kind]
        days = sorted({o.day for o in obs})
        nums = defaultdict(list)
        for o in obs:
            if o.value_numeric is not None:
                nums[o.day].append(o.value_numeric)
        label = _label(kind)
        if nums:
            dm = [mean(v) for _, v in sorted(nums.items())]
            if len(dm) == 1:
                body = f"{_fmt(kind, dm[0])} on 1 day this week."
            else:
                body = (f"Recorded on {_plural(len(days), 'day')} this week: average {_fmt(kind, mean(dm))}, "
                        f"range {_fmt(kind, min(dm))} to {_fmt(kind, max(dm))}, latest {_fmt(kind, dm[-1])}.")
            stats = {"days": len(days), "observations": len(obs), "mean": round(mean(dm), 2), "min": round(min(dm), 2),
                     "max": round(max(dm), 2), "latest": round(dm[-1], 2)}
        else:
            counts = defaultdict(int)
            for o in obs:
                counts[o.value_text] += 1
            body = f"Recorded on {_plural(len(days), 'day')} this week: " + ", ".join(
                f"{str(v).replace('_', ' ')} ×{n}" for v, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))) + "."
            stats = {"days": len(days), "observations": len(obs), "values": dict(counts)}
        out.append({"id": f"recorded:{kind}", "type": "recorded_observation", "kind": kind, "label": label,
                    "title": label.capitalize(), "body": body, "stats": stats})
    return out


def _layout(report: dict, p: _Prepared, prog: dict) -> list:
    wk = p.weekly_window
    cov = report["coverage"]
    week_obs = p.in_window(wk.week_start, wk.week_end)
    days_n = len({o.day for o in week_obs})
    base = prog["levels"]["baseline"]
    assoc = prog["levels"]["associations"]
    recorded = _recorded_observations(p)
    kinds_this_week = {o.kind for o in week_obs}
    not_recorded = [k for k in list(MORNING_CORE) + list(EVENING_CORE) if k not in kinds_this_week]

    if week_obs:
        headline = (f"You recorded {_plural(len(week_obs), 'observation')} on {days_n} of 7 days "
                    f"({wk.week_start.isoformat()} to {wk.week_end.isoformat()}).")
        ov_status = "ready"
    else:
        last = prog["coverage"]["last_day"]
        headline = ("Nothing was recorded in the last 7 days" + (f"; your most recent record is from {last}." if last else ".")
                    + " A check-in starts this week's picture.")
        ov_status = "empty"
    overview = {"id": "overview", "title": "Weekly overview", "status": ov_status, "summary": headline,
                "facts": {"days_recorded": days_n, "observations": len(week_obs), "week": [wk.week_start.isoformat(), wk.week_end.isoformat()],
                          "highest_level": prog["highest_level"], "report_state": report["report_state"]},
                "items": [], "collapsible": False, "collapsed": False}

    recorded_sec = {"id": "recorded_observations", "title": "What you recorded", "status": "ready" if recorded else "empty",
                    "summary": (f"{_plural(len(recorded), 'measurement')} recorded this week." if recorded else "No measurements recorded this week."),
                    "items": recorded, "not_recorded": [{"kind": k, "label": _label(k)} for k in not_recorded] if week_obs else [],
                    "collapsible": False, "collapsed": False}

    week_prelim = _preliminary(p, since=wk.week_start)
    descriptive = [i for i in week_prelim if i["id"].startswith("preliminary:")]
    desc_sec = {"id": "descriptive_insights", "title": "What the numbers show", "status": "ready" if descriptive else "locked",
                "summary": ("Descriptive changes between your recorded days this week." if descriptive else
                            f"Needs at least {PRELIM_MIN_DAYS} days with the same measurement this week."),
                "items": descriptive, "collapsible": False, "collapsed": False}

    emerging = [i for i in week_prelim if i["id"].startswith("recurring:")] + list(assoc["items"])
    emerging_sec = {"id": "emerging_patterns", "title": "Emerging patterns", "status": "ready" if emerging else "locked",
                    "summary": ("Recurring observations and engine-tested signals. All are observational." if emerging else
                                f"Recurring observations need {RECURRING_MIN_DAYS} recorded days; associations come only from the research engine. {assoc['requires']}"),
                    "items": emerging, "pair_progress": assoc["pair_progress"], "collapsible": False, "collapsed": False}

    base_items = [c for c in base["comparisons"] if c["status"] in ("changed", "stable")]
    base_sec = {"id": "personal_baseline", "title": "Compared with your baseline", "status": "ready" if base_items else "locked",
                "summary": ("Last 7 days compared with the 21 days before." if base_items else base["requires"]),
                "items": base_items, "comparison_period": base["comparison_period"], "progress": base["progress"],
                "collapsible": False, "collapsed": False}

    details = []
    for f in report["findings"]:
        if f["type"] == "insufficient_evidence":
            details.append({"id": f["id"], "title": f["title"], "body": f["body"]})
    for pr in base["progress"]:
        details.append({"id": f"progress:{pr['kind']}", "title": pr["label"].capitalize(),
                        "body": (f"{pr['week_days']} of {pr['need_week_days']} days this week; "
                                 f"{pr['baseline_days']} of {pr['need_baseline_days']} baseline days.")})
    coverage_sec = {"id": "coverage_limitations", "title": "Data coverage and limits", "status": "ready",
                    "summary": (f"{cov['observations']} observations on {cov['days']} days this week; "
                                f"{cov['baseline_observations']} observations on {cov['baseline_days']} baseline days."),
                    "coverage": cov, "warnings": report["data_quality_warnings"], "limitations": report["limitations"],
                    "details": details, "details_title": "Why some comparisons are not available yet",
                    "items": [], "collapsible": True, "collapsed": True}

    next_sec = {"id": "next_observations", "title": "Suggested next observations",
                "status": "ready" if prog["next_observations"] else "empty",
                "summary": "Observation only. This is not medical advice.", "items": prog["next_observations"],
                "collapsible": False, "collapsed": False}
    return [overview, recorded_sec, desc_sec, emerging_sec, base_sec, coverage_sec, next_sec]


def build_weekly_report(records: Iterable, *, user_id, tz_name: Optional[str], now: datetime, profile: Optional[dict] = None,
                        engine_run: Optional[dict] = None, engine_candidates: Optional[list] = None,
                        newest_ingested_at: Optional[datetime] = None, current_model_version: Optional[str] = None) -> dict:
    """The weekly report with a progressive ``layout``.

    ``weekly.build_weekly_report`` stays the source of the evidence-gated ``findings`` (contract
    ``nexgene.weekly_report/1`` is unchanged). ``layout`` is additive: an ordered list of sections that
    always carries what *is* available, so insufficient history can never replace the whole report.
    """
    recs = list(records)
    common = dict(user_id=user_id, tz_name=tz_name, now=now, engine_run=engine_run, engine_candidates=engine_candidates,
                  newest_ingested_at=newest_ingested_at, current_model_version=current_model_version)
    report = W.build_weekly_report(recs, profile=profile, **common)
    p = _Prepared(recs, tz_name, now)
    prog = build_progressive(recs, _prepared=p, **common)
    report["layout_version"] = LAYOUT_VERSION
    report["layout"] = _layout(report, p, prog)
    report["highest_level"] = prog["highest_level"]
    return report
