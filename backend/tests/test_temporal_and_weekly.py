"""Temporal contract + weekly-report honesty tests.

Runs under pytest (the repo's runner) and plain ``python -m unittest`` (no third-party imports).
All data here is SYNTHETIC and built in memory; nothing touches a real account or database.
"""
import json
import random
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.temporal import (  # noqa: E402
    EventTimeError, bucket_observations, event_time_of, validate_event_time, weekly_window,
)
from backend.app.weekly import build_weekly_report  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)  # a Sunday
MODEL = "nexgene-test-model/1"

FORBIDDEN_PHRASES = [  # generic statements that previously overclaimed; must never return
    "starting to become interesting", "one good thing", "protect your usual sleep window",
    "useful bit of context", "small, human read",
]


def obs(kind, value, days_ago, *, hour=9, ingested=None, text=None):
    when = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0)
    return NS(kind=kind, value_numeric=value, value_text=text, observed_at=when, recorded_at=ingested or NOW)


def series(kind, values_by_days_ago, **kw):
    return [obs(kind, v, d, **kw) for d, v in values_by_days_ago.items()]


def report(records, **kw):
    kw.setdefault("user_id", 1)
    kw.setdefault("tz_name", "UTC")
    kw.setdefault("now", NOW)
    return build_weekly_report(records, **kw)


def stable_view(r):
    """Report minus fields that legitimately vary between runs."""
    return json.dumps({k: v for k, v in r.items() if k not in ("timings_ms",)}, sort_keys=True, default=str)


def all_text(r):
    return " ".join(f["title"] + " " + f["body"] for f in r["findings"]).lower() + " " + (r["experiment"] or "").lower()


class TemporalContract(unittest.TestCase):
    def test_ninety_days_imported_today_land_in_their_event_periods(self):
        # every row was INGESTED now, but its event happened 0..89 days ago
        recs = [obs("sleep_duration", 7.0, d) for d in range(90)]
        b = bucket_observations(recs, weekly_window(NOW, "UTC"), NOW)
        self.assertEqual((len(b.week), len(b.baseline), b.outside_window), (7, 21, 62))

    def test_before_fix_behaviour_is_demonstrably_wrong(self):
        # Reproduction of the defect: keying on recorded_at puts ALL 90 imported days in "this week".
        recs = [obs("sleep_duration", 7.0, d) for d in range(90)]
        legacy = [NS(**{**r.__dict__, "observed_at": None}) for r in recs]  # event time discarded
        b = bucket_observations(legacy, weekly_window(NOW, "UTC"), NOW)
        self.assertEqual(len(b.week), 90 - b.duplicates_dropped)  # 1 distinct instant -> collapsed
        self.assertTrue(b.legacy_event_time > 0)

    def test_weekly_report_uses_event_time_for_imported_history(self):
        vals = {d: (6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5)) for d in range(28)}
        r = report(series("sleep_duration", vals))
        self.assertEqual(r["coverage"]["days"], 7)
        self.assertEqual(r["coverage"]["baseline_days"], 21)
        self.assertEqual(r["coverage"]["observations"], 7)

    def test_baseline_excludes_the_week_it_is_compared_with(self):
        vals = {d: (6.0 if d < 7 else 8.0 + (0.1 if d % 2 else -0.1)) for d in range(28)}
        f = [x for x in report(series("sleep_duration", vals))["findings"] if x["id"].endswith(":change")][0]
        self.assertAlmostEqual(f["evidence"]["baseline_mean"], 8.0, delta=0.05)  # not blended with the 6.0 week
        self.assertAlmostEqual(f["evidence"]["delta"], -2.0, delta=0.05)

    def test_import_order_does_not_change_the_result(self):
        recs = series("sleep_duration", {d: 6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5) for d in range(28)})
        recs += series("focus", {d: 5 + (d % 3) for d in range(28)})
        baseline = stable_view(report(recs))
        for seed in range(5):
            shuffled = recs[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(stable_view(report(shuffled)), baseline)

    def test_duplicate_import_does_not_inflate_counts_or_active_days(self):
        recs = series("sleep_duration", {d: 7.0 for d in range(10)})
        once, twice = report(recs), report(recs + [NS(**r.__dict__) for r in recs])
        self.assertEqual(once["coverage"]["observations"], twice["coverage"]["observations"])
        self.assertEqual(once["coverage"]["days"], twice["coverage"]["days"])
        self.assertEqual(twice["coverage"]["duplicates_dropped"], 10)
        self.assertIn("duplicates_dropped", [w["code"] for w in twice["data_quality_warnings"]])

    def test_import_batches_on_different_days_do_not_create_extra_active_days(self):
        same_event = obs("energy", 6, 1)
        batch2 = NS(**{**same_event.__dict__, "recorded_at": NOW + timedelta(days=3)})
        r = report([same_event, batch2], now=NOW + timedelta(days=3))
        self.assertEqual(r["coverage"]["observations"] + r["coverage"]["baseline_observations"], 1)

    def test_timezone_boundary_uses_local_calendar_days(self):
        now = datetime(2026, 10, 25, 0, 10, tzinfo=UTC)  # 01:10 on the 25th in Lagos (UTC+1)
        late = NS(kind="energy", value_numeric=6.0, value_text=None, recorded_at=now,
                  observed_at=datetime(2026, 10, 18, 23, 30, tzinfo=UTC))  # 00:30 on the 19th in Lagos
        lagos = bucket_observations([late], weekly_window(now, "Africa/Lagos"), now)
        utc = bucket_observations([late], weekly_window(now, "UTC"), now)
        self.assertEqual((len(lagos.week), len(lagos.baseline)), (1, 0))   # local day 19th = first day of week
        self.assertEqual((len(utc.week), len(utc.baseline)), (0, 1))       # UTC day 18th = baseline

    def test_missing_event_time_is_quarantined_not_treated_as_now(self):
        ghost = NS(kind="energy", value_numeric=9.0, value_text=None, observed_at=None, recorded_at=None)
        r = report([ghost])
        self.assertEqual(r["status"], "not_ready")
        self.assertEqual(r["coverage"]["quarantined"]["missing_event_time"], 1)
        self.assertEqual(event_time_of(ghost), (None, "missing"))

    def test_future_dated_observation_is_quarantined(self):
        future = obs("energy", 9.0, -3)
        r = report([future])
        self.assertEqual(r["coverage"]["quarantined"]["future_dated"], 1)
        self.assertEqual(r["coverage"]["observations"], 0)

    def test_legacy_rows_are_flagged_not_silently_trusted(self):
        legacy = NS(kind="energy", value_numeric=6.0, value_text=None, observed_at=None, recorded_at=NOW - timedelta(days=1))
        r = report([legacy])
        self.assertEqual(r["coverage"]["legacy_event_time_observations"], 1)
        self.assertIn("legacy_event_time", [w["code"] for w in r["data_quality_warnings"]])

    def test_client_event_time_validation(self):
        with self.assertRaises(EventTimeError) as c:
            validate_event_time(datetime(2026, 10, 1, 8, 0), now=NOW)          # naive
        self.assertEqual(c.exception.code, "naive_event_time")
        with self.assertRaises(EventTimeError) as c:
            validate_event_time(NOW + timedelta(hours=2), now=NOW)             # future
        self.assertEqual(c.exception.code, "future_event_time")
        with self.assertRaises(EventTimeError):
            validate_event_time(NOW - timedelta(days=20000), now=NOW)
        self.assertEqual(validate_event_time(None, now=NOW), NOW)             # live check-in
        past = datetime(2026, 10, 1, 8, 0, tzinfo=timezone(timedelta(hours=1)))
        self.assertEqual(validate_event_time(past, now=NOW), past.astimezone(UTC))

    def test_naive_storage_values_are_read_as_utc(self):
        naive = NS(kind="energy", value_numeric=5.0, value_text=None, observed_at=None, recorded_at=datetime(2026, 10, 24, 8, 0))
        when, basis = event_time_of(naive)
        self.assertEqual((when.tzinfo, basis), (UTC, "recorded_at_legacy"))


class WeeklyHonesty(unittest.TestCase):
    def assert_no_forbidden(self, r):
        text = all_text(r) + " " + r.get("message", "").lower()
        for p in FORBIDDEN_PHRASES:
            self.assertNotIn(p, text)

    def test_no_observations(self):
        r = report([])
        self.assertEqual((r["status"], r["report_state"], r["findings"], r["sections"]), ("not_ready", "no_data", [], []))
        self.assertIsNone(r["experiment"])
        self.assert_no_forbidden(r)

    def test_sparse_observations_state_what_is_missing(self):
        r = report(series("sleep_duration", {1: 7.0, 2: 6.5}) + series("focus", {1: 6, 2: 6}))
        self.assertEqual(r["report_state"], "insufficient_data")
        f = r["findings"][0]
        self.assertEqual(f["type"], "insufficient_evidence")
        self.assertIn("need 3", f["body"])
        self.assertNotIn("candidate_association", [x["type"] for x in r["findings"]])
        self.assertIsNone(r["experiment"])
        self.assert_no_forbidden(r)

    def test_one_week_only_cannot_support_a_comparison(self):
        r = report(series("sleep_duration", {d: 7.0 for d in range(7)}))
        self.assertEqual([f["type"] for f in r["findings"]], ["insufficient_evidence"])
        self.assertIn("three weeks before", r["findings"][0]["body"])
        self.assertEqual(r["report_state"], "insufficient_data")

    def test_recording_sleep_and_focus_together_is_not_an_association(self):
        recs = series("sleep_duration", {d: 7.0 + (d % 2) for d in range(28)}) + series("focus", {d: 5 + (d % 2) for d in range(28)})
        r = report(recs)
        self.assertTrue(all(f["type"] in ("descriptive_summary", "insufficient_evidence") for f in r["findings"]))
        self.assertNotIn("relationship", all_text(r))
        self.assert_no_forbidden(r)

    def test_consistent_weeks_say_no_meaningful_change(self):
        r = report(series("sleep_duration", {d: 7.5 + (0.5 if d % 2 else -0.5) for d in range(28)}))
        self.assertEqual(r["findings"][0]["id"], "descriptive_summary:no_meaningful_change")
        self.assertIn("No meaningful change has been established", r["findings"][0]["body"])
        self.assertIsNone(r["experiment"])

    def test_meaningful_change_is_descriptive_and_bounded(self):
        r = report(series("sleep_duration", {d: 6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5) for d in range(28)}))
        f = r["findings"][0]
        self.assertEqual(f["type"], "descriptive_summary")
        self.assertIn("does not show why", f["body"])
        self.assertIsNone(f["confidence"])
        for key in ("question", "observed_variable", "period", "outcome_measured", "confounders", "supports_if", "weakens_if"):
            self.assertTrue(r["experiment_detail"][key])
        self.assertIn("not a medical test", r["experiment_detail"]["scope_note"])

    def test_conflicting_values_on_one_day_are_averaged_not_double_counted(self):
        recs = series("energy", {0: 2}) + [obs("energy", 10, 0, hour=11)] + series("energy", {1: 6, 2: 6})
        r = report(recs)
        self.assertEqual(r["coverage"]["days"], 3)
        self.assertEqual(r["coverage"]["observations"], 4)

    def test_outlier_driven_change_is_withheld(self):
        wk = {0: 7.5, 1: 7.5, 2: 7.5, 3: 7.5, 4: 4.0}
        base = {d: (7.5, 7.0, 8.0)[d % 3] for d in range(7, 28)}  # median 7.5
        r = report(series("sleep_duration", {**wk, **base}))
        self.assertFalse([f for f in r["findings"] if f["id"].endswith(":change")])
        self.assertIn("outlier_sensitive", [w["code"] for w in r["data_quality_warnings"]])

    def test_future_dated_row_on_the_same_day_is_not_counted(self):
        later_today = obs("energy", 10, 0, hour=18)   # 18:00 when "now" is 12:00
        self.assertEqual(report([later_today])["coverage"]["quarantined"]["future_dated"], 1)

    def test_text_only_and_missing_numeric_values_do_not_crash(self):
        recs = [obs("morning_context", None, d, text="none") for d in range(5)] + [NS(kind="energy", value_numeric=None, value_text=None, observed_at=NOW, recorded_at=NOW)]
        r = report(recs)
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["report_state"], "insufficient_data")

    def test_repeated_identical_values_are_handled_without_division_by_zero(self):
        flat = {d: 7.5 for d in range(7, 28)}
        same = report(series("sleep_duration", {**{d: 7.5 for d in range(7)}, **flat}))
        self.assertEqual(same["findings"][0]["id"], "descriptive_summary:no_meaningful_change")
        shifted = report(series("sleep_duration", {**{d: 6.5 for d in range(7)}, **flat}))
        self.assertTrue(shifted["findings"][0]["id"].endswith(":change"))

    def test_findings_are_capped_and_ranked_not_padded(self):
        kinds = ["sleep_duration", "energy", "stress", "focus", "mood"]
        recs = []
        for k in kinds:
            recs += series(k, {d: (3.0 if d < 7 else 7.0 + (0.5 if d % 2 else -0.5)) for d in range(28)})
        r = report(recs)
        self.assertLessEqual(len([f for f in r["findings"] if f["id"].endswith(":change")]), 3)

    def test_every_finding_carries_traceable_evidence(self):
        r = report(series("sleep_duration", {d: 6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5) for d in range(28)}))
        for f in r["findings"]:
            self.assertTrue(f["evidence"]["source"])
            self.assertIn(f["type"], ("descriptive_summary", "insufficient_evidence", "hypothesis", "candidate_association", "validated_finding"))

    def test_report_is_reproducible_and_pure(self):
        recs = series("sleep_duration", {d: 7.0 for d in range(14)})
        a, b = report(recs), report(recs)
        self.assertEqual(a["report_id"], b["report_id"])
        self.assertEqual(stable_view(a), stable_view(b))
        self.assertEqual(a["schema_version"], "nexgene.weekly_report/1")
        self.assertFalse(a["generation"]["language_model_used"])


def candidate(**kw):
    base = dict(user_id=1, hypothesis_id="h1", exposure="sleep_duration", outcome="focus", lag=1, status="SUPPORTED",
                evidence_tier="ERL-2", evidence_label="Robust association", q_value=0.01, n_pairs=60, effect_estimate=0.3,
                confidence=0.7, model_version=MODEL, last_tested_at=NOW.isoformat(), echo_of=None)
    base.update(kw)
    return base


def run(status="completed", age_minutes=60, **kw):
    base = dict(id=7, status=status, created_at=NOW - timedelta(minutes=age_minutes), model_version=MODEL, summary={"engine": "NexGene Research Engine v0.4.0", "window_days": 90})
    base.update(kw)
    return base


def with_engine(cands, run_=None, **kw):
    recs = series("sleep_duration", {d: 7.0 + (d % 2) for d in range(14)})
    return report(recs, engine_run=run_, engine_candidates=cands, current_model_version=MODEL,
                  newest_ingested_at=kw.pop("newest_ingested_at", NOW - timedelta(days=1)), **kw)


class EngineIntegration(unittest.TestCase):
    def test_valid_result_reaches_report_with_provenance(self):
        r = with_engine([candidate()], run())
        f = [x for x in r["findings"] if x["type"] == "candidate_association"][0]
        self.assertEqual(f["evidence"]["run_id"], 7)
        self.assertEqual(f["evidence"]["hypothesis_id"], "h1")
        self.assertIn("does not show that one causes the other", f["body"])
        self.assertEqual(r["engine"]["state"], "current")

    def test_missing_engine_result_fabricates_nothing(self):
        r = with_engine([], None)
        self.assertEqual(r["engine"]["state"], "not_run")
        self.assertFalse([f for f in r["findings"] if f["evidence"]["source"] == "research_engine"])

    def test_failed_run_is_not_mistaken_for_success(self):
        r = with_engine([candidate()], run("failed", failure_category="panel_build_error"))
        self.assertEqual(r["engine"]["state"], "failed")
        self.assertFalse([f for f in r["findings"] if f["evidence"]["source"] == "research_engine"])
        self.assertIn("engine_failed", [w["code"] for w in r["data_quality_warnings"]])
        self.assertEqual(r["report_state"], "completed_with_warnings" if r["findings"][0]["type"] != "insufficient_evidence" else r["report_state"])

    def test_foreign_user_result_cannot_enter_the_report(self):
        r = with_engine([candidate(user_id=2), candidate(hypothesis_id="h2", user_id=None)], run())
        self.assertFalse([f for f in r["findings"] if f["evidence"]["source"] == "research_engine"])
        self.assertEqual(r["engine"]["excluded"]["unauthorised"], 2)

    def test_evidence_tiers_map_to_distinct_finding_types(self):
        cases = {"ERL-0": None, "ERL-1": "hypothesis", "ERL-2": "candidate_association", "ERL-3": "candidate_association",
                 "ERL-4": "validated_finding", "ERL-5": "validated_finding"}
        for tier, expected in cases.items():
            r = with_engine([candidate(evidence_tier=tier)], run())
            got = [f["type"] for f in r["findings"] if f["evidence"]["source"] == "research_engine"]
            self.assertEqual(got, [expected] if expected else [], tier)

    def test_exploratory_signal_is_not_called_a_finding_or_discovery(self):
        r = with_engine([candidate(evidence_tier="ERL-1", status="TESTING")], run())
        f = [x for x in r["findings"] if x["type"] == "hypothesis"][0]
        self.assertIn("not a finding", f["body"])
        self.assertNotIn("discover", f["body"].lower())

    def test_unreportable_statuses_and_versions_are_excluded(self):
        for bad in (candidate(status="FALSIFIED"), candidate(status="GENERATED"), candidate(model_version="old/0"), candidate(echo_of="x")):
            r = with_engine([bad], run())
            self.assertFalse([f for f in r["findings"] if f["evidence"]["source"] == "research_engine"])

    def test_new_observations_after_a_run_make_it_stale_and_say_so(self):
        r = with_engine([candidate()], run(), newest_ingested_at=NOW)
        self.assertEqual(r["engine"]["state"], "stale")
        self.assertIn("new_observations_since_run", r["engine"]["stale_reasons"])
        f = [x for x in r["findings"] if x["type"] == "candidate_association"][0]
        self.assertTrue(any("earlier analysis run" in l for l in f["limitations"]))

    def test_old_run_and_version_change_are_stale(self):
        self.assertEqual(with_engine([], run(age_minutes=60 * 24 * 8))["engine"]["state"], "stale")
        self.assertIn("model_version_changed", with_engine([], run(model_version="old/0"))["engine"]["stale_reasons"])

    def test_interrupted_and_running_are_distinguished(self):
        self.assertEqual(with_engine([], run("running", age_minutes=2))["engine"]["state"], "running")
        self.assertEqual(with_engine([], run("running", age_minutes=45))["engine"]["state"], "interrupted")

    def test_completed_run_with_no_eligible_findings_is_reported_as_such(self):
        self.assertEqual(with_engine([], run())["engine"]["state"], "no_eligible_findings")

    def test_descriptive_statistics_are_never_labelled_as_validated(self):
        r = with_engine([], run())
        self.assertFalse([f for f in r["findings"] if f["type"] in ("validated_finding", "candidate_association")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
