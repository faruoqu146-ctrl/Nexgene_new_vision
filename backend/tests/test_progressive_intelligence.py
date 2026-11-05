"""Progressive-intelligence tests.

Runs under pytest (the repo's runner) and plain ``python -m unittest`` (no third-party imports beyond numpy,
which the research package already needs). All data is SYNTHETIC and built in memory.

Covers: one-, two- and three-day users, incomplete morning/evening check-ins, missing variables, sufficient and
insufficient baseline coverage, repeated check-ins, a new observation appearing immediately, sparse weekly
reports, user isolation, determinism, honesty (no association without the engine, no causal wording) and the
check-in contract between the UI and the API validator.
"""
import json
import random
import shutil
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import weekly as W  # noqa: E402
from backend.app.checkin import CheckinValueError, normalize_values  # noqa: E402
from backend.app.progressive import build_progressive, build_weekly_report  # noqa: E402
from backend.app.research.config import DEFAULT_CONFIG  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 30, 14, 0, tzinfo=UTC)   # a Friday, 14:00 UTC
MODEL = "nexgene-test-model/1"

# wording that must never appear in generated, user-facing statements about their data
CAUSAL_OR_DIAGNOSTIC = ["because", "causes", "caused", "leads to", "due to", "diagnos", "you have ", "treat", "cure", "prove"]


def obs(kind, value, days_ago, *, hour=8, text=None, minute=0):
    when = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=minute)
    return NS(kind=kind, value_numeric=value, value_text=text, observed_at=when, recorded_at=when)


def morning(days_ago, sleep=7.0, quality=6, energy=7, context="none", hour=8):
    return [obs("sleep_duration", sleep, days_ago, hour=hour), obs("sleep_quality", quality, days_ago, hour=hour),
            obs("energy", energy, days_ago, hour=hour), obs("morning_context", None, days_ago, hour=hour, text=context)]


def evening(days_ago, mood=6, stress=4, focus=6, hour=9):
    return [obs("mood", mood, days_ago, hour=hour), obs("stress", stress, days_ago, hour=hour), obs("focus", focus, days_ago, hour=hour)]


def prog(records, **kw):
    kw.setdefault("user_id", 1)
    kw.setdefault("tz_name", "UTC")
    kw.setdefault("now", NOW)
    return build_progressive(records, **kw)


def weekly(records, **kw):
    kw.setdefault("user_id", 1)
    kw.setdefault("tz_name", "UTC")
    kw.setdefault("now", NOW)
    return build_weekly_report(records, **kw)


def user_text(p):
    """Every sentence the progressive payload shows about the user's data."""
    parts = [i["text"] for i in p["today"]["interpretation"]]
    parts += [s["title"] + " " + s["body"] for s in p["signals"]["signals"]]
    parts += [n["text"] for n in p["next_observations"]]
    parts += [i["title"] + " " + i["body"] for i in p["levels"]["preliminary_patterns"]["items"]]
    parts += [c.get("title", "") + " " + c.get("body", "") for c in p["levels"]["baseline"]["comparisons"]]
    return " ".join(parts).lower()


def candidate(**kw):
    base = dict(user_id=1, hypothesis_id="h1", exposure="sleep_duration", outcome="focus", lag=1, status="SUPPORTED",
                evidence_tier="ERL-2", evidence_label="Robust association", q_value=0.01, n_pairs=60, effect_estimate=0.3,
                confidence=0.7, model_version=MODEL, last_tested_at=NOW.isoformat(), echo_of=None)
    base.update(kw)
    return base


def engine_run(**kw):
    base = dict(id=7, status="completed", created_at=NOW - timedelta(minutes=60), model_version=MODEL,
                summary={"engine": "NexGene Research Engine v0.4.0", "window_days": 90})
    base.update(kw)
    return base


class EvidenceLevels(unittest.TestCase):
    def test_empty_user_gets_a_welcome_not_a_failure(self):
        p = prog([])
        self.assertEqual((p["highest_level"], p["today"]["state"]), (0, "empty"))
        self.assertEqual(p["signals"]["status"], "starting")
        self.assertEqual(p["levels"]["observations"]["status"], "locked")
        self.assertTrue(p["today"]["interpretation"][0]["text"].startswith("Nothing has been recorded today"))

    def test_one_day_user_gets_immediate_observations_and_no_trend(self):
        p = prog(morning(0, sleep=6.5, quality=6, energy=8))
        self.assertEqual((p["highest_level"], p["available_levels"]), (1, [1]))
        by_kind = {v["kind"]: v for v in p["today"]["values"]}
        self.assertEqual(by_kind["sleep_duration"]["display"], "6.5 h")
        self.assertEqual(by_kind["energy"]["display"], "8/10")
        statuses = {k: v["status"] for k, v in p["levels"].items()}
        self.assertEqual(statuses["observations"], "available")
        self.assertEqual(statuses["preliminary_patterns"], "locked")
        self.assertEqual(statuses["baseline"], "locked")
        self.assertIn(statuses["associations"], ("locked", "collecting"))
        self.assertEqual(p["levels"]["preliminary_patterns"]["items"], [])
        self.assertEqual(p["signals"]["signals"][0]["type"], "observation")
        self.assertEqual(p["signals"]["signals"][0]["level"], 1)
        text = user_text(p)
        self.assertIn("6.5 h", text)
        self.assertIn("a single day cannot show how they relate", text)
        self.assertIn("quality is around the middle of the 0-10 scale; energy is toward the high end", text)   # one sentence, one capital
        for bad in CAUSAL_OR_DIAGNOSTIC:
            self.assertNotIn(bad, text)

    def test_one_day_both_check_ins_complete(self):
        p = prog(morning(0) + evening(0))
        self.assertEqual((p["today"]["state"], p["today"]["check_ins_complete"]), ("complete", 2))
        self.assertFalse([n for n in p["next_observations"] if n["id"] in ("next:morning", "next:evening")])

    def test_two_day_user_gets_preliminary_patterns_with_sample_size_disclosed(self):
        p = prog(morning(1, sleep=7.5, energy=6) + morning(0, sleep=6.0, energy=8))
        self.assertEqual(p["available_levels"], [1, 2])
        item = {i["kind"]: i for i in p["levels"]["preliminary_patterns"]["items"]}["sleep_duration"]
        self.assertEqual(item["sample"]["days"], 2)
        self.assertEqual(item["direction"], "lower")
        self.assertIsNone(item["confidence"])
        self.assertIn("not a trend", item["body"])
        self.assertTrue(any("too few to call a trend" in l for l in item["limitations"]))
        self.assertTrue(any("no significance test" in l.lower() for l in item["limitations"]))
        self.assertEqual(p["levels"]["baseline"]["status"], "locked")
        self.assertEqual(p["levels"]["associations"]["items"], [])

    def test_two_similar_days_are_described_as_similar_not_as_a_change(self):
        p = prog(morning(1, sleep=7.0) + morning(0, sleep=7.2))
        item = {i["kind"]: i for i in p["levels"]["preliminary_patterns"]["items"]}["sleep_duration"]
        self.assertEqual(item["direction"], "similar")
        self.assertIn("similar", item["body"])

    def test_three_day_user_sees_range_and_recurring_observations(self):
        recs = morning(2, context="fatigue") + morning(1, context="none") + morning(0, context="fatigue")
        p = prog(recs)
        items = {i["id"]: i for i in p["levels"]["preliminary_patterns"]["items"]}
        self.assertIn("ranged from", items["preliminary:sleep_duration"]["body"])
        rec = items["recurring:morning_context:fatigue"]
        self.assertEqual(rec["stats"], {"occurrences": 2, "days": 3})
        self.assertIn("does not say why", rec["body"])
        self.assertEqual(p["levels"]["baseline"]["status"], "locked")   # 3 days is not a baseline
        self.assertNotIn("recurring:morning_context:none", items)       # "nothing unusual" is not a recurring finding

    def test_incomplete_morning_checkin_names_what_is_missing(self):
        p = prog([obs("energy", 7, 0)])
        m = p["today"]["periods"]["morning"]
        self.assertEqual((m["status"], m["missing_core"]), ("partial", ["sleep_duration", "sleep_quality"]))
        self.assertEqual(p["today"]["periods"]["evening"]["status"], "missing")
        self.assertIn("incomplete", user_text(p))
        self.assertTrue(any(n["id"] == "next:morning" for n in p["next_observations"]))

    def test_incomplete_evening_checkin_names_what_is_missing(self):
        p = prog(morning(0) + [obs("mood", 6, 0, hour=9)])
        e = p["today"]["periods"]["evening"]
        self.assertEqual((e["status"], e["missing_core"]), ("partial", ["stress", "focus"]))
        self.assertEqual(p["today"]["check_ins_complete"], 1)

    def test_missing_individual_variables_do_not_crash_or_get_filled_in(self):
        recs = [obs("sleep_duration", 7.0 + (d % 2), d) for d in range(5)]
        p = prog(recs)
        self.assertEqual(set(p["coverage"]["days_by_kind"]), {"sleep_duration"})
        self.assertEqual(p["levels"]["associations"]["pair_progress"], [])
        self.assertEqual([v["kind"] for v in p["today"]["values"]], ["sleep_duration"])
        self.assertTrue(p["levels"]["preliminary_patterns"]["items"])

    def test_skipped_answers_are_not_observations(self):
        recs = morning(0, context="skipped") + [obs("activity_level", None, 0, text="skipped")]
        p = prog(recs)
        self.assertNotIn("morning_context", [v["kind"] for v in p["today"]["values"]])
        self.assertEqual({s["kind"] for s in p["today"]["skipped"]}, {"morning_context", "activity_level"})
        self.assertEqual(p["coverage"]["skipped_answers"], 2)
        self.assertEqual(p["coverage"]["total_observations"], 3)


class Baseline(unittest.TestCase):
    def test_thresholds_were_not_lowered(self):
        # Guard: this feature must not make the interface look smarter by relaxing the science.
        self.assertEqual((W.MIN_WEEK_DAYS, W.MIN_BASELINE_DAYS), (3, 4))
        self.assertEqual((DEFAULT_CONFIG.min_pairs, DEFAULT_CONFIG.min_pairs_support), (14, 21))

    def test_sufficient_baseline_coverage_compares_windows_and_shows_its_inputs(self):
        recs = [obs("sleep_duration", 6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5), d) for d in range(28)]
        p = prog(recs)
        base = p["levels"]["baseline"]
        self.assertEqual((base["status"], p["highest_level"]), ("available", 4))
        c = base["comparisons"][0]
        self.assertEqual((c["kind"], c["status"], c["n_week_days"], c["n_baseline_days"]), ("sleep_duration", "changed", 7, 21))
        self.assertAlmostEqual(c["delta"], -1.5, delta=0.1)
        self.assertEqual(base["comparison_period"]["recent"], ["2026-10-24", "2026-10-30"])
        self.assertEqual(base["comparison_period"]["baseline"], ["2026-10-03", "2026-10-23"])
        self.assertTrue(any("does not show why" in l for l in c["limitations"]))
        self.assertTrue(any(s["type"] == "baseline" and s["level"] == 4 for s in p["signals"]["signals"]))

    def test_baseline_agrees_with_the_weekly_report(self):
        recs = [obs("sleep_duration", 6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5), d) for d in range(28)]
        legacy = W.build_weekly_report(recs, user_id=1, tz_name="UTC", now=NOW)
        f = [x for x in legacy["findings"] if x["id"].endswith(":change")][0]
        c = prog(recs)["levels"]["baseline"]["comparisons"][0]
        self.assertEqual((c["delta"], c["week_mean"], c["baseline_mean"]), (f["evidence"]["delta"], f["evidence"]["week_mean"], f["evidence"]["baseline_mean"]))

    def test_stable_week_is_reported_as_stable(self):
        recs = [obs("sleep_duration", 7.5 + (0.5 if d % 2 else -0.5), d) for d in range(28)]
        c = prog(recs)["levels"]["baseline"]["comparisons"][0]
        self.assertEqual(c["status"], "stable")
        self.assertIn("No meaningful change has been established", c["body"])

    def test_insufficient_baseline_coverage_says_how_far_along_the_user_is(self):
        recs = [obs("sleep_duration", 7.0 + (d % 2), d) for d in range(5)]
        base = prog(recs)["levels"]["baseline"]
        self.assertEqual((base["status"], base["comparisons"]), ("locked", []))
        pr = base["progress"][0]
        self.assertEqual((pr["kind"], pr["week_days"], pr["need_week_days"], pr["baseline_days"], pr["need_baseline_days"]),
                         ("sleep_duration", 5, 3, 0, 4))
        self.assertTrue(any("three weeks before" in m for m in pr["missing"]))

    def test_recent_week_is_never_part_of_its_own_baseline(self):
        recs = [obs("sleep_duration", 6.0 if d < 7 else 8.0 + (0.1 if d % 2 else -0.1), d) for d in range(28)]
        c = prog(recs)["levels"]["baseline"]["comparisons"][0]
        self.assertAlmostEqual(c["baseline_mean"], 8.0, delta=0.05)


class Associations(unittest.TestCase):
    def perfectly_correlated(self):
        return [r for d in range(30) for r in (obs("sleep_duration", 6 + (d % 4), d), obs("focus", 4 + (d % 4), d, hour=9))]

    def test_no_association_is_ever_invented_without_the_engine(self):
        p = prog(self.perfectly_correlated())
        a = p["levels"]["associations"]
        self.assertEqual(a["items"], [])
        self.assertEqual(a["status"], "collecting")
        self.assertNotIn("moved together", user_text(p))
        self.assertEqual(a["engine"]["state"], "not_run")
        self.assertFalse(any(s["type"] == "association" for s in p["signals"]["signals"]))

    def test_pair_progress_reports_distance_to_the_existing_minimum(self):
        recs = [r for d in range(3) for r in (obs("sleep_duration", 7, d), obs("focus", 6, d, hour=9))]
        pr = prog(recs)["levels"]["associations"]["pair_progress"][0]
        self.assertEqual((pr["paired_days"], pr["needed_to_test"], pr["remaining_to_test"], pr["needed_for_robust_association"]), (3, 14, 11, 21))

    def test_engine_result_is_adapted_with_its_caveats(self):
        p = prog(self.perfectly_correlated(), engine_run=engine_run(), engine_candidates=[candidate()], current_model_version=MODEL,
                 newest_ingested_at=NOW - timedelta(days=1))
        a = p["levels"]["associations"]
        self.assertEqual(a["status"], "available")
        f = a["items"][0]
        self.assertEqual(f["type"], "candidate_association")
        self.assertIn("does not show that one causes the other", f["body"])
        self.assertIn(3, p["available_levels"])   # 30 days of data also unlocks the baseline, so the highest level is 4
        sig = [s for s in p["signals"]["signals"] if s["type"] == "association"][0]
        self.assertEqual(sig["evidence"]["evidence_tier"], "ERL-2")

    def test_foreign_user_engine_results_are_excluded(self):
        p = prog(self.perfectly_correlated(), engine_run=engine_run(), engine_candidates=[candidate(user_id=2, hypothesis_id="other-user-h")],
                 current_model_version=MODEL, newest_ingested_at=NOW - timedelta(days=1))
        a = p["levels"]["associations"]
        self.assertEqual(a["items"], [])
        self.assertEqual(a["engine"]["excluded"]["unauthorised"], 1)
        self.assertNotIn("other-user-h", json.dumps(p))

    def test_failed_engine_is_not_presented_as_success(self):
        p = prog(self.perfectly_correlated(), engine_run=engine_run(status="failed", failure_category="panel_build_error"),
                 engine_candidates=[candidate()], current_model_version=MODEL)
        self.assertEqual(p["levels"]["associations"]["items"], [])
        self.assertEqual(p["levels"]["associations"]["engine"]["state"], "failed")


class RepeatedAndImmediate(unittest.TestCase):
    def test_repeated_checkin_same_day_uses_latest_for_display_and_the_mean_for_summaries(self):
        recs = [obs("energy", 4, 0, hour=7), obs("energy", 8, 0, hour=11)]
        p = prog(recs)
        e = p["today"]["values"][0]
        self.assertEqual((e["value"], e["n_readings"], e["day_mean"]), (8, 2, 6.0))
        self.assertIn("energy", p["today"]["repeated_readings"])
        self.assertEqual(p["coverage"]["total_days"], 1)

    def test_exact_duplicate_rows_count_once(self):
        a = obs("energy", 7, 0)
        p = prog([a, NS(**a.__dict__)])
        self.assertEqual(p["coverage"]["total_observations"], 1)
        self.assertEqual(p["coverage"]["duplicates_dropped"], 1)
        self.assertEqual(p["today"]["values"][0]["n_readings"], 1)

    def test_a_new_observation_appears_in_the_snapshot_immediately(self):
        before = prog(morning(1))
        self.assertEqual(before["today"]["values"], [])
        after = prog(morning(1) + morning(0, hour=13))   # saved at 13:00; "now" is 14:00
        self.assertEqual([v["kind"] for v in after["today"]["values"]], ["sleep_duration", "sleep_quality", "energy", "morning_context"])
        self.assertEqual(after["today"]["periods"]["morning"]["status"], "complete")
        self.assertEqual(after["available_levels"], [1, 2])   # day 2 unlocked the descriptive level in the same response
        self.assertEqual(after["signals"]["signals"][0]["type"], "observation")

    def test_future_dated_rows_are_not_shown_as_recorded(self):
        p = prog([obs("energy", 7, 0, hour=18)])
        self.assertEqual(p["today"]["values"], [])
        self.assertEqual(p["coverage"]["quarantined"]["future_dated"], 1)

    def test_local_calendar_day_not_utc_day(self):
        late = NS(kind="energy", value_numeric=6.0, value_text=None, recorded_at=NOW, observed_at=datetime(2026, 10, 29, 23, 30, tzinfo=UTC))
        lagos, utc = prog([late], tz_name="Africa/Lagos"), prog([late], tz_name="UTC")
        self.assertEqual(len(lagos["today"]["values"]), 1)    # 00:30 on the 30th in Lagos
        self.assertEqual(len(utc["today"]["values"]), 0)      # still the 29th in UTC
        self.assertEqual(prog([late], tz_name="Not/AZone")["data_quality_warnings"][0]["code"], "timezone_fallback_utc")

    def test_output_is_deterministic_and_order_independent(self):
        recs = [r for d in range(20) for r in morning(d, sleep=6 + (d % 3)) + evening(d, mood=4 + (d % 5))]
        base = json.dumps(prog(recs), sort_keys=True, default=str)
        for seed in range(4):
            shuffled = recs[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(json.dumps(prog(shuffled), sort_keys=True, default=str), base)

    def test_no_language_model_and_no_causal_or_diagnostic_wording(self):
        recs = [r for d in range(12) for r in morning(d, sleep=5 + (d % 4)) + evening(d, stress=3 + (d % 5))]
        p = prog(recs)
        self.assertFalse(p["generation"]["language_model_used"])
        text = user_text(p)
        for bad in CAUSAL_OR_DIAGNOSTIC:
            self.assertNotIn(bad, text)


class SparseWeeklyReport(unittest.TestCase):
    IDS = ["overview", "recorded_observations", "descriptive_insights", "emerging_patterns", "personal_baseline", "coverage_limitations", "next_observations"]

    def test_one_day_report_is_a_real_report_not_a_single_insufficient_card(self):
        r = weekly(morning(0, sleep=6.5, energy=8))
        self.assertEqual([s["id"] for s in r["layout"]], self.IDS)
        by = {s["id"]: s for s in r["layout"]}
        self.assertEqual((by["overview"]["status"], by["recorded_observations"]["status"], by["next_observations"]["status"]), ("ready",) * 3)
        self.assertIn("1 of 7 days", by["overview"]["summary"])
        energy = [i for i in by["recorded_observations"]["items"] if i["kind"] == "energy"][0]
        self.assertEqual(energy["body"], "8/10 on 1 day this week.")   # a single reading is not an "average" or a "range"
        self.assertEqual({i["kind"] for i in by["recorded_observations"]["items"]}, {"sleep_duration", "sleep_quality", "energy", "morning_context"})
        self.assertEqual(by["personal_baseline"]["status"], "locked")
        # legacy contract is untouched: the evidence-gated findings still say what is missing
        self.assertEqual(r["report_state"], "insufficient_data")
        self.assertEqual(r["findings"][0]["type"], "insufficient_evidence")
        self.assertEqual(r["schema_version"], "nexgene.weekly_report/1")

    def test_missing_data_explanations_live_in_a_collapsed_section(self):
        by = {s["id"]: s for s in weekly(morning(0))["layout"]}
        cov = by["coverage_limitations"]
        self.assertEqual((cov["collapsible"], cov["collapsed"]), (True, True))
        self.assertTrue(any(d["id"] == "insufficient_evidence:comparison" for d in cov["details"]))
        self.assertEqual(cov["coverage"]["days"], 1)
        # nothing else in the report is collapsible: the explanation does not replace the content
        self.assertEqual([s["id"] for s in weekly(morning(0))["layout"] if s["collapsible"]], ["coverage_limitations"])

    def test_week_with_no_data_still_returns_a_useful_layout(self):
        r = weekly([obs("sleep_duration", 7.0, 10 + d) for d in range(5)])
        self.assertEqual((r["status"], r["report_state"], r["sections"]), ("not_ready", "no_data", []))
        by = {s["id"]: s for s in r["layout"]}
        self.assertEqual(by["overview"]["status"], "empty")
        self.assertIn("Nothing was recorded in the last 7 days", by["overview"]["summary"])
        self.assertIn("most recent record is from 2026-10-20", by["overview"]["summary"])

    def test_three_day_week_has_descriptive_changes_and_still_no_association(self):
        r = weekly(morning(2, sleep=7.5) + morning(1, sleep=7.0) + morning(0, sleep=6.0) + evening(2) + evening(1) + evening(0))
        by = {s["id"]: s for s in r["layout"]}
        self.assertEqual(by["descriptive_insights"]["status"], "ready")
        self.assertFalse([i for i in by["emerging_patterns"]["items"] if i.get("type") in ("candidate_association", "validated_finding")])
        self.assertNotIn("relationship", json.dumps(by["descriptive_insights"]).lower())

    def test_full_history_adds_baseline_without_dropping_earlier_sections(self):
        recs = [obs("sleep_duration", 6.0 if d < 7 else 7.5 + (0.5 if d % 2 else -0.5), d) for d in range(28)]
        by = {s["id"]: s for s in weekly(recs)["layout"]}
        self.assertEqual(by["personal_baseline"]["status"], "ready")
        self.assertEqual(by["personal_baseline"]["comparison_period"]["recent"], ["2026-10-24", "2026-10-30"])
        self.assertEqual(by["personal_baseline"]["items"][0]["n_baseline_days"], 21)
        self.assertEqual(by["recorded_observations"]["status"], "ready")

    def test_weekly_report_is_reproducible(self):
        recs = [obs("sleep_duration", 7.0 + (d % 2), d) for d in range(14)]
        a, b = weekly(recs), weekly(recs)
        strip = lambda r: json.dumps({k: v for k, v in r.items() if k != "timings_ms"}, sort_keys=True, default=str)
        self.assertEqual(strip(a), strip(b))
        self.assertEqual(a["report_id"], b["report_id"])


class CheckinContract(unittest.TestCase):
    KW = dict(max_keys=16, max_text=256)

    def test_the_ui_evening_payload_is_accepted(self):
        # This exact shape used to be rejected with HTTP 422, so no evening check-in could ever be saved.
        out = normalize_values({"mood": 8, "stress": 3, "focus": 6, "activity_level": "light", "diet_quality": "good",
                                "caffeine": 1, "alcohol": 0, "nicotine": "none"}, **self.KW)
        self.assertEqual(out["activity_level"], "light")
        self.assertEqual(out["nicotine"], "none")
        self.assertEqual(out["caffeine"], 1.0)

    def test_digit_strings_from_cached_clients_become_numbers(self):
        out = normalize_values({"caffeine": "2", "alcohol": "3"}, **self.KW)
        self.assertEqual(out, {"caffeine": 2.0, "alcohol": 3.0})

    def test_skipped_answers_are_dropped(self):
        out = normalize_values({"energy": 7, "morning_context": "skipped", "activity_level": "skipped"}, **self.KW)
        self.assertEqual(out, {"energy": 7.0})
        self.assertEqual(normalize_values({"morning_context": "skipped"}, **self.KW), {})

    def test_bad_values_are_still_rejected(self):
        for bad in ({"energy": "abc"}, {"energy": 11}, {"energy": -1}, {"sleep_duration": 25}, {"made_up_kind": 1}, {"morning_context": "x" * 257},
                    {"activity_level": "huge"}, {"energy": float("nan")}, {"energy": float("inf")}, {"nicotine": "chain"}):
            with self.assertRaises(CheckinValueError, msg=str(bad)):
                normalize_values(bad, **self.KW)
        with self.assertRaises(CheckinValueError):
            normalize_values({f"k{i}": 1 for i in range(17)}, **self.KW)

    def test_numeric_value_is_not_silently_stored_as_text(self):
        self.assertIsInstance(normalize_values({"energy": "7"}, **self.KW)["energy"], float)

    def test_every_choice_the_mobile_ui_offers_is_accepted_by_the_api_rules(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not available")
        script = (
            "const fs=require('fs'),vm=require('vm');const src=fs.readFileSync(process.argv[1],'utf8');"
            "const m=src.match(/const M=(\\[.*?\\]);\\nconst E=(\\[.*?\\]);\\n/s);"
            "const ctx={};vm.runInNewContext('M='+m[1]+';E='+m[2],ctx);"
            "const out=[];for(const arr of [ctx.M,ctx.E])for(const q of arr)for(const o of q[3])out.push([q[0],o[2]]);"
            "console.log(JSON.stringify(out));")
        res = subprocess.run([node, "-e", script, str(ROOT / "mobile" / "app.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(res.returncode, 0, res.stderr)
        choices = json.loads(res.stdout)
        self.assertGreater(len(choices), 40)
        for kind, value in choices:
            try:
                normalize_values({kind: value}, **self.KW)
            except CheckinValueError as exc:  # pragma: no cover - failure message only
                self.fail(f"the UI offers {kind}={value!r} but the API would reject it: {exc}")


if __name__ == "__main__":
    unittest.main()
