#!/usr/bin/env python3
"""Generate the versioned synthetic historical check-in dataset (deterministic)."""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATASET_ID = "nexgene-syn-student-30d"
DATASET_VERSION = "1.0.0"
GENERATOR_VERSION = "syn-hist-gen-1.0.0"
SEED = 20261024
DAYS = 30
SUBJECT_ID = "SYN-STUDENT-001"
SCENARIO_ID = "university_exam_stress_v1"

MORNING = ["sleep_duration", "sleep_quality", "energy", "morning_context"]
EVENING = ["mood", "stress", "focus", "activity_level", "diet_quality", "caffeine", "alcohol", "nicotine"]


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _r1(x: float) -> float:
    return round(float(x), 1)


def build_dataset() -> dict:
    rng = random.Random(SEED)
    end = datetime(2026, 10, 23, tzinfo=timezone.utc)
    start = end - timedelta(days=DAYS - 1)
    exam_start_idx = DAYS - 10
    records: list[dict] = []
    prev_sleep = 7.2
    missingness: dict[str, list[str]] = {}

    for d in range(DAYS):
        day = (start + timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
        weekday = day.weekday()
        exam = d >= exam_start_idx
        workday = weekday < 5
        skip_morning = d in {4, 17}
        skip_evening = d in {11, 22, 8}
        misses = []
        if skip_morning:
            misses.append("morning")
        if skip_evening:
            misses.append("evening")
        if misses:
            missingness[str(d)] = misses

        stress_base = 4.5 if workday else 3.5
        if exam:
            stress_base += 2.2 if workday else 1.2
        if weekday == 0:
            stress_base += 0.5

        sleep_target = 7.0 if workday else 7.6
        if exam:
            sleep_target -= 0.9
        sleep_duration = _clamp(rng.gauss(sleep_target, 0.5), 4.5, 9.5)
        sleep_debt = max(0.0, 7.0 - prev_sleep)
        sleep_quality = _clamp(
            rng.gauss(6.4 + 0.3 * (sleep_duration - 7.0) - (0.8 if exam else 0), 1.0), 2.0, 10.0
        )
        energy = _clamp(rng.gauss(6.5 - 0.4 * sleep_debt - (0.9 if exam else 0), 0.9), 2.0, 10.0)
        stress = _clamp(rng.gauss(stress_base, 1.0), 1.0, 9.5)
        mood = _clamp(rng.gauss(6.5 - 0.3 * (stress - 5) + 0.2 * (energy - 6), 0.9), 2.0, 10.0)
        focus = _clamp(
            rng.gauss(6.3 - 0.35 * (stress - 5) - 0.25 * sleep_debt - (0.7 if exam else 0), 1.0),
            2.0,
            10.0,
        )
        activity = _clamp(rng.gauss(5.5 if workday else 6.2, 1.2) - (0.8 if exam else 0), 1.0, 9.0)
        diet = _clamp(rng.gauss(6.0 - (0.6 if exam else 0), 1.1), 2.0, 9.5)
        caffeine = _clamp(rng.gauss(1.5 + (1.2 if exam else 0), 0.8), 0.0, 5.0)
        alcohol = 0.0 if workday or exam else _clamp(rng.gauss(0.4, 0.5), 0.0, 3.0)
        if rng.random() < 0.7:
            alcohol = 0.0
        nicotine = 0.0
        contexts = ["none", "none", "none", "fatigue", "headache", "none"]
        morning_context = contexts[rng.randint(0, len(contexts) - 1)]
        if exam and rng.random() < 0.35:
            morning_context = "fatigue"
        prev_sleep = sleep_duration

        values = {
            "sleep_duration": _r1(sleep_duration),
            "sleep_quality": _r1(sleep_quality),
            "energy": _r1(energy),
            "morning_context": morning_context,
            "mood": _r1(mood),
            "stress": _r1(stress),
            "focus": _r1(focus),
            "activity_level": _r1(activity),
            "diet_quality": _r1(diet),
            "caffeine": _r1(caffeine),
            "alcohol": _r1(alcohol),
            "nicotine": _r1(nicotine),
        }
        morning_at = day.replace(hour=7, minute=10) + timedelta(minutes=rng.randint(0, 35))
        evening_at = day.replace(hour=21, minute=5) + timedelta(minutes=rng.randint(0, 45))
        phase = "exam" if exam else "baseline"

        if not skip_morning:
            for kind in MORNING:
                records.append(
                    {
                        "kind": kind,
                        "value": values[kind],
                        "observed_at": morning_at.isoformat().replace("+00:00", "Z"),
                        "period": "morning",
                        "source_type": "user-entered",
                        "quality_flag": "self_reported",
                        "day_index": d,
                        "scenario_phase": phase,
                    }
                )
        if not skip_evening:
            for kind in EVENING:
                records.append(
                    {
                        "kind": kind,
                        "value": values[kind],
                        "observed_at": evening_at.isoformat().replace("+00:00", "Z"),
                        "period": "evening",
                        "source_type": "user-entered",
                        "quality_flag": "self_reported",
                        "day_index": d,
                        "scenario_phase": phase,
                    }
                )

    payload = {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "generator_version": GENERATOR_VERSION,
        "random_seed": SEED,
        "synthetic": True,
        "scenario_id": SCENARIO_ID,
        "subject_id": SUBJECT_ID,
        "subject_profile": {
            "label": "Fictional university student (synthetic)",
            "age_range": "18-24",
            "occupation": "Student",
            "student": True,
            "study_field": "Computer science",
            "timezone": "Africa/Lagos",
            "country": "Nigeria",
        },
        "window": {
            "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(),
            "days": DAYS,
        },
        "missingness": missingness,
        "observation_count": len(records),
        "records": records,
    }
    raw = json.dumps({k: v for k, v in payload.items()}, sort_keys=True, separators=(",", ":")).encode()
    payload["content_hash"] = hashlib.sha256(raw).hexdigest()
    return payload


def build_ground_truth(payload: dict) -> dict:
    return {
        "dataset_id": payload["dataset_id"],
        "dataset_version": payload["dataset_version"],
        "content_hash": payload["content_hash"],
        "synthetic": True,
        "planted_patterns": [
            {
                "id": "GT-001",
                "name": "exam_period_elevated_stress",
                "window": "last_10_days",
                "direction": "stress higher in exam phase than baseline",
                "variables": ["stress"],
            },
            {
                "id": "GT-002",
                "name": "exam_period_reduced_sleep",
                "window": "last_10_days",
                "direction": "sleep_duration lower in exam phase than baseline",
                "variables": ["sleep_duration"],
            },
            {
                "id": "GT-003",
                "name": "sleep_energy_coupling",
                "window": "full_30_days",
                "direction": "shorter sleep co-occurs with lower energy (noisy)",
                "variables": ["sleep_duration", "energy"],
            },
        ],
        "negative_controls": [
            {"id": "GT-NC-001", "name": "nicotine_no_signal", "variables": ["nicotine"]},
            {"id": "GT-NC-002", "name": "alcohol_sparse_no_causal_claim", "variables": ["alcohol"]},
        ],
        "limitations": [
            "Synthetic data only; not real participant observations.",
            "Patterns are designed, not discovered from nature.",
            "Does not validate clinical or predictive performance.",
        ],
    }


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    payload = build_dataset()
    gt = build_ground_truth(payload)
    (out_dir / "dataset_v1.json").write_text(json.dumps(payload, indent=2))
    (out_dir / "ground_truth_v1.json").write_text(json.dumps(gt, indent=2))
    print(
        json.dumps(
            {
                "status": "ok",
                "dataset_id": payload["dataset_id"],
                "version": payload["dataset_version"],
                "records": payload["observation_count"],
                "content_hash": payload["content_hash"],
                "files": ["dataset_v1.json", "ground_truth_v1.json"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
