#!/usr/bin/env python3
"""Score synthetic import against pre-registered ground truth (offline metrics)."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def phase_means(records: list[dict], kind: str) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if r.get("kind") != kind:
            continue
        if not isinstance(r.get("value"), (int, float)):
            continue
        phase = r.get("scenario_phase") or "unknown"
        buckets[phase].append(float(r["value"]))
    return {k: statistics.mean(v) for k, v in buckets.items() if v}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=HERE / "dataset_v1.json")
    parser.add_argument("--ground-truth", type=Path, default=HERE / "ground_truth_v1.json")
    args = parser.parse_args()
    ds = load_json(args.dataset)
    gt = load_json(args.ground_truth)
    records = ds["records"]

    results = []
    sm = phase_means(records, "stress")
    results.append({
        "id": "GT-001",
        "metric": "mean_stress",
        "baseline": sm.get("baseline"),
        "exam": sm.get("exam"),
        "pass": sm.get("exam", 0) > sm.get("baseline", 99),
    })
    sl = phase_means(records, "sleep_duration")
    results.append({
        "id": "GT-002",
        "metric": "mean_sleep_duration",
        "baseline": sl.get("baseline"),
        "exam": sl.get("exam"),
        "pass": sl.get("exam", 99) < sl.get("baseline", 0),
    })
    nic = [float(r["value"]) for r in records if r.get("kind") == "nicotine" and isinstance(r.get("value"), (int, float))]
    results.append({
        "id": "GT-NC-001",
        "metric": "nicotine_all_zero",
        "n": len(nic),
        "max": max(nic) if nic else None,
        "pass": bool(nic) and max(nic) == 0.0,
    })

    report = {
        "synthetic": True,
        "dataset_id": ds.get("dataset_id"),
        "dataset_version": ds.get("dataset_version"),
        "content_hash": ds.get("content_hash"),
        "observation_count": len(records),
        "results": results,
        "limitations": gt.get("limitations"),
        "interpretation_boundary": (
            "These metrics evaluate the synthetic dataset design and import integrity only. "
            "They are not clinical evidence and do not validate predictive performance."
        ),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
