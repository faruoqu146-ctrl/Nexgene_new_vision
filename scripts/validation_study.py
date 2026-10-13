"""Resumable validation study for the NexGene Research Engine (synthetic data with known ground truth).

    python scripts/validation_study.py run    --out validation_runs [--budget 150]   # resumable; repeat until 'remaining 0'
    python scripts/validation_study.py report --out validation_runs
    python -m backend.app.research.validate --extras --out extras.json               # randomisation / forward / drift / timing

Jobs write one JSON file each, so an interrupted run resumes where it stopped (use --budget to cap one invocation in seconds).
All seeds are fixed; with the same NumPy version results reproduce exactly. They say nothing about real people.
"""
import argparse
import collections
import glob
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.app.research import validate as V  # noqa: E402

SEED = 20261011
S_NULL = [dict(T=60, ar=0.3, missing=0.10, weekly=0.5), dict(T=90, ar=0.5, missing=0.10, weekly=0.5),
          dict(T=90, ar=0.8, missing=0.15, weekly=0.5), dict(T=120, ar=0.5, missing=0.20, weekly=0.5, round_scale=True)]
S_PAIR = [dict(T=60, ar=0.0, missing=0.10, weekly=0.6, trend=0.4), dict(T=60, ar=0.5, missing=0.10, weekly=0.6, trend=0.4),
          dict(T=60, ar=0.8, missing=0.10, weekly=0.6, trend=0.4), dict(T=90, ar=0.5, missing=0.20, weekly=0.6, trend=0.4, round_scale=True),
          dict(T=45, ar=0.6, missing=0.15, weekly=0.6, trend=0.4)]


def jobs():
    out = []
    for si, st in enumerate(S_NULL):
        out += [(f"null_{si}_{k}", "null", st, 25, SEED + 1000 * si + k) for k in range(6)]
    for T in (60, 90, 120):
        out += [(f"mixed_{T}_{k}", "mixed", dict(T=T, ar=0.5, missing=0.10, weekly=0.5, trend=0.2), 20, SEED + T * 10 + k) for k in range(6)]
    for si, st in enumerate(S_PAIR):
        out += [(f"pair_{si}_{k}", "pair", st, 300, SEED + 77 + si * 10 + k) for k in range(3)]
    return out


def run(out_dir: str, budget: float) -> None:
    os.makedirs(out_dir, exist_ok=True)
    t0, done, skipped = time.time(), 0, 0
    for name, kind, st, n, seed in jobs():
        path = os.path.join(out_dir, name + ".json")
        if os.path.exists(path):
            skipped += 1
            continue
        if time.time() - t0 > budget:
            break
        if kind == "null":
            res = V.null_study(n, seed, [st])
        elif kind == "mixed":
            res = V.mixed_study(n, seed, st, strengths=(0.4, 0.7, 1.0, 1.4))
        else:
            res = V.pairwise_calibration_study(n, seed, [st])
        with open(path, "w") as fh:
            json.dump(res, fh)
        done += 1
    remaining = sum(1 for name, *_ in jobs() if not os.path.exists(os.path.join(out_dir, name + ".json")))
    print(f"ran {done} jobs ({time.time() - t0:.0f}s); already done {skipped}; remaining {remaining} of {len(jobs())}")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def summarise(out_dir: str) -> dict:
    def load(prefix):
        return [json.load(open(p)) for p in sorted(glob.glob(os.path.join(out_dir, prefix + "_*.json")))]
    out = {}
    tot, by, setting = collections.Counter(), collections.defaultdict(collections.Counter), {}
    for r in load("null"):
        for k in ("n_panels", "any_claim_erl2", "any_claim_erl3", "claims_erl2", "candidates", "nominal_p_le_05", "ci_excludes_zero"):
            tot[k] += r[k]
        a = r["by_setting"][0]
        key = json.dumps(a["setting"], sort_keys=True)
        setting[key] = a["setting"]
        for k in ("panels", "any_claim_erl2", "candidates", "nominal_p_le_05"):
            by[key][k] += a[k]
    out["null"] = {"panels": tot["n_panels"], "false_claim_panels_erl2": tot["any_claim_erl2"], "false_claim_rate": tot["any_claim_erl2"] / max(1, tot["n_panels"]),
                   "false_claim_rate_ci95": wilson(tot["any_claim_erl2"], tot["n_panels"]), "panels_with_erl3_claim": tot["any_claim_erl3"],
                   "total_erl2_claims": tot["claims_erl2"], "candidates": tot["candidates"],
                   "type1_per_candidate_nominal_05": tot["nominal_p_le_05"] / max(1, tot["candidates"]),
                   "ci95_excludes_zero_rate": tot["ci_excludes_zero"] / max(1, tot["candidates"]),
                   "by_setting": [{"setting": setting[k], "panels": c["panels"], "false_claim_rate": c["any_claim_erl2"] / c["panels"],
                                   "false_claim_rate_ci95": wilson(c["any_claim_erl2"], c["panels"]), "type1_per_candidate": c["nominal_p_le_05"] / c["candidates"]}
                                  for k, c in by.items()]}
    # mixed + pair aggregation truncated for length - full script continues below in source
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", default="validation_runs")
    r.add_argument("--budget", type=float, default=150.0)
    sub.add_parser("report").add_argument("--out", default="validation_runs")
    ns = ap.parse_args()
    if ns.cmd == "run":
        run(ns.out, ns.budget)
    else:
        print(json.dumps(summarise(ns.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
