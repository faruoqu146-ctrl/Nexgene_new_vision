"""Reproducible validation studies on synthetic data with known ground truth.

    python -m backend.app.research.validate --quick            # a few minutes
    python -m backend.app.research.validate --full --out validation.json

What these studies can and cannot show
  * They measure the engine's error control and power on *simulated* people whose true
    effects are planted, under autocorrelation, weekly cycles, trend, missing days and
    discretised 0-10 scales.
  * They do NOT show that the engine works on real people; real data violate the
    simulation's assumptions in ways nobody can enumerate.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from typing import Optional, Sequence

import numpy as np

from .config import DEFAULT_CONFIG
from .discovery import analyze_panel
from .simulate import simulate_panel

NAMES = ["caffeine", "alcohol", "activity_duration", "mood", "energy", "focus", "stress", "sleep_quality"]


def _claims(res, level: int = 2):
    return [c for c in res.candidates if c["tier"]["level"] >= level]


def null_study(n_panels: int, seed: int, settings: Sequence[dict]) -> dict:
    """Panels with NO real relationships. Any ERL>=2 claim is a false discovery."""
    rng = np.random.default_rng(seed)
    out = {"n_panels": 0, "any_claim_erl2": 0, "any_claim_erl3": 0, "claims_erl2": 0, "candidates": 0,
           "nominal_p_le_05": 0, "ci_excludes_zero": 0, "by_setting": []}
    per_setting = max(1, n_panels // len(settings))
    for st in settings:
        agg = {"setting": st, "panels": 0, "any_claim_erl2": 0, "candidates": 0, "nominal_p_le_05": 0}
        for _ in range(per_setting):
            p = simulate_panel(rng, names=NAMES, effects=[], **st)
            res = analyze_panel(p, DEFAULT_CONFIG)
            c2 = _claims(res, 2)
            agg["panels"] += 1
            agg["any_claim_erl2"] += bool(c2)
            agg["candidates"] += len(res.candidates)
            agg["nominal_p_le_05"] += sum(c["inference"]["p_combined"] <= 0.05 for c in res.candidates)
            out["n_panels"] += 1
            out["any_claim_erl2"] += bool(c2)
            out["any_claim_erl3"] += bool(_claims(res, 3))
            out["claims_erl2"] += len(c2)
            out["candidates"] += len(res.candidates)
            out["nominal_p_le_05"] += sum(c["inference"]["p_combined"] <= 0.05 for c in res.candidates)
            out["ci_excludes_zero"] += sum(not (c["effect"]["r_ci95"][0] <= 0 <= c["effect"]["r_ci95"][1]) for c in res.candidates)
        agg["false_claim_rate_per_panel"] = agg["any_claim_erl2"] / max(1, agg["panels"])
        agg["type1_per_candidate"] = agg["nominal_p_le_05"] / max(1, agg["candidates"])
        out["by_setting"].append(agg)
    n = max(1, out["n_panels"])
    out["false_claim_rate_per_panel"] = out["any_claim_erl2"] / n
    out["type1_per_candidate_at_nominal_05"] = out["nominal_p_le_05"] / max(1, out["candidates"])
    out["ci95_noncoverage_of_zero"] = out["ci_excludes_zero"] / max(1, out["candidates"])
    return out


def pairwise_calibration_study(n_pairs: int, seed: int, settings: Sequence[dict]) -> dict:
    """Type I error of each p-value on pairs of INDEPENDENT series: naive Pearson vs the engine's components."""
    from . import inference as inf
    from .special import t_two_sided_p
    cfg = DEFAULT_CONFIG
    rng = np.random.default_rng(seed)
    methods = ["naive_pearson", "hac", "bartlett_effective_n", "shift_calibrated", "combined_reported"]
    out = []
    for st in settings:
        kern = inf.NullKernel(st["T"], max(cfg.lags), cfg.shift_buffer)
        rej = {m: [0, 0, 0] for m in methods}
        n = 0
        for _ in range(n_pairs):
            p = simulate_panel(rng, names=["x", "y"], effects=[], **st)
            D = inf.build_design(p.ordinals, p.weekdays)
            px, py = inf.prepare_variable("x", p.variables["x"], D, cfg), inf.prepare_variable("y", p.variables["y"], D, cfg)
            for lag in (0, 1):
                s = inf.screen_pair(px, py, lag, kern, cfg)
                if s is None:
                    continue
                a, b, _ = inf.pair_arrays(px.raw, py.raw, lag)
                r = float(np.corrcoef(a, b)[0, 1])
                pv = {"naive_pearson": t_two_sided_p(r * math.sqrt((len(a) - 2) / (1 - r * r)), len(a) - 2), "hac": s.p_hac,
                      "bartlett_effective_n": s.p_eff, "shift_calibrated": s.p_shift_gauss, "combined_reported": s.p_combined}
                n += 1
                for m, val in pv.items():
                    if val is None:
                        continue
                    for i, al in enumerate((0.05, 0.01, 0.001)):
                        rej[m][i] += val <= al
        out.append({"setting": st, "n_tests": n, "rejection_rate_at_alpha_0.05_0.01_0.001": {m: [round(x / max(1, n), 4) for x in v] for m, v in rej.items()}})
    return {"settings": out}


def _true_ids(effects):
    ids = set()
    for (x, y, lag, _b) in effects:
        ids.add(f"{x}->{y}@{lag}")
        if lag == 0:
            ids.add(f"{y}->{x}@0")
    return ids


def mixed_study(n_panels: int, seed: int, setting: dict, strengths: Sequence[float]) -> dict:
    """Panels with a few planted effects among many nulls.

    Every ERL>=2 claim is classified against the known generating graph:
      planted   - exactly a planted (exposure, outcome, lag) relationship
      echo      - the planted pair but another lag or orientation. Persistence in real series makes these
                  genuinely correlated; they are statistically non-null, not false discoveries
      spurious  - a pair with NO planted connection (a true null, the thing FDR control is about)
    ERL>=3 claims additionally carry a direction: correct only if it names the planted exposure -> outcome.
    """
    rng = np.random.default_rng(seed)
    plan = [("activity_duration", "mood", 1), ("stress", "focus", 0), ("caffeine", "sleep_quality", 1), ("alcohol", "energy", 1)]
    negative = {("stress", "focus"), ("caffeine", "sleep_quality")}
    pairs = {frozenset((x, y)): (x, y, lag) for (x, y, lag) in plan}
    per = {s: {"detected_erl2": 0, "detected_erl3": 0, "n": 0, "sign_correct": 0} for s in strengths}
    cls = {"planted": 0, "echo": 0, "spurious": 0, "erl3_total": 0, "erl3_planted_direction": 0, "erl3_wrong_direction": 0,
           "panels_with_spurious": 0, "claims_total": 0, "fdp_spurious_sum": 0.0, "panels_with_claims": 0, "erl3_fdp_sum": 0.0,
           "panels_with_erl3": 0}
    panels = 0
    for _ in range(n_panels):
        beta = float(strengths[panels % len(strengths)])
        effects = [(x, y, lag, (-beta if (x, y) in negative else beta)) for (x, y, lag) in plan]
        p = simulate_panel(rng, names=NAMES, effects=effects, **setting)
        res = analyze_panel(p, DEFAULT_CONFIG)
        truth = _true_ids(effects)
        had_spurious = False
        panel_claims = panel_spurious = panel_erl3 = panel_erl3_wrong = 0
        for c in _claims(res, 2):
            panel_claims += 1
            cls["claims_total"] += 1
            key = frozenset((c["exposure"], c["outcome"]))
            if c["id"] in truth:
                kind = "planted"
            elif key in pairs:
                kind = "echo"
            else:
                kind = "spurious"
                had_spurious = True
            cls[kind] += 1
            panel_spurious += kind == "spurious"
            if c["tier"]["level"] >= 3:
                cls["erl3_total"] += 1
                panel_erl3 += 1
                if key in pairs and (c["exposure"], c["outcome"]) == pairs[key][:2] and pairs[key][2] >= 1:
                    cls["erl3_planted_direction"] += 1
                else:
                    cls["erl3_wrong_direction"] += 1
                    panel_erl3_wrong += 1
        cls["panels_with_spurious"] += had_spurious
        if panel_claims:
            cls["panels_with_claims"] += 1
            cls["fdp_spurious_sum"] += panel_spurious / panel_claims
        if panel_erl3:
            cls["panels_with_erl3"] += 1
            cls["erl3_fdp_sum"] += panel_erl3_wrong / panel_erl3
        by = {c["id"]: c for c in res.candidates}
        for (x, y, lag, b) in effects:
            cid = f"{x}->{y}@{lag}"
            c = by.get(cid) or by.get(f"{y}->{x}@0")
            per[beta]["n"] += 1
            if c is None:
                continue
            per[beta]["detected_erl2"] += c["tier"]["level"] >= 2
            per[beta]["detected_erl3"] += c["tier"]["level"] >= 3
            per[beta]["sign_correct"] += (c["effect"]["r_adj"] > 0) == (b > 0)
        panels += 1
    return {
        "setting": setting, "n_panels": panels, "claims": cls,
        "power_by_strength": {
            str(s): {"power_erl2": v["detected_erl2"] / max(1, v["n"]), "power_erl3": v["detected_erl3"] / max(1, v["n"]),
                     "sign_accuracy": v["sign_correct"] / max(1, v["n"]), "n_effects": v["n"],
                     "detected_erl2": v["detected_erl2"], "detected_erl3": v["detected_erl3"], "sign_correct": v["sign_correct"]} for s, v in per.items()
        },
    }


def experiment_size_study(n: int, seed: int, configs: Sequence[tuple]) -> dict:
    """Size of the exact sign-flip randomisation test when outcomes are autocorrelated and unaffected by assignment."""
    import hashlib as _h
    from .experiment import PROTOCOL, signflip_p
    rng = np.random.default_rng(seed)
    out = []
    for (n_blocks, period_len, ar) in configs:
        rej = 0
        for _ in range(n):
            T = n_blocks * 2 * period_len
            e = np.zeros(T)
            for t in range(1, T):
                e[t] = ar * e[t - 1] + math.sqrt(1 - ar * ar) * rng.standard_normal()
            sd = int(rng.integers(1, 10 ** 9))
            d = []
            for b in range(n_blocks):
                first_b = bool(_h.sha256(f"{PROTOCOL}:{sd}:{b}".encode()).digest()[0] & 1)
                seg = e[b * 2 * period_len:(b + 1) * 2 * period_len]
                f, s_ = seg[:period_len].mean(), seg[period_len:].mean()
                d.append((f - s_) if first_b else (s_ - f))
            rej += signflip_p(np.array(d), sd)[0] <= 0.05
        out.append({"n_blocks": n_blocks, "period_len": period_len, "outcome_ar": ar, "n": n, "rejection_rate_at_0.05": rej / n})
    return {"configs": out}


def spc_study(n: int, seed: int) -> dict:
    """False-alarm and detection rates of the drift detectors on AR(1) series with 15% missing days."""
    from datetime import date, timedelta
    from .spc import analyze_drift
    rng = np.random.default_rng(seed)
    dates = [date(2026, 1, 1) + timedelta(days=i) for i in range(90)]

    def ar(phi):
        x = np.zeros(140)
        for t in range(1, 140):
            x[t] = phi * x[t - 1] + math.sqrt(1 - phi * phi) * rng.standard_normal()
        return x[50:]

    rows = []
    for shift_sd, last in [(0.0, 0), (1.5, 7), (1.5, 14), (2.5, 7), (1.0, 21)]:
        cu = rw = 0
        for _ in range(n):
            v = 5 + ar(0.5) * 1.2
            if shift_sd:
                v[90 - last:] += shift_sd * 1.2
            v[rng.random(90) < 0.15] = np.nan
            r = analyze_drift(v, dates, DEFAULT_CONFIG)
            cu += bool(r.get("shift_detected"))
            rw += bool(r.get("recent_window", {}).get("notable"))
        rows.append({"shift_sd": shift_sd, "last_days": last, "n": n, "cusum_alarm_rate": cu / n, "recent_window_alarm_rate": rw / n})
    return {"scenarios": rows}


def forecast_study(n: int, seed: int, train: int = 80, total: int = 130) -> dict:
    """Locked-model forward test: a data-selected spurious candidate vs a real planted effect, scored on unseen days."""
    from .forecast import freeze_model, score_frozen
    names = ["caffeine", "alcohol", "mood", "energy", "sleep_quality"]
    rng = np.random.default_rng(seed)
    out = {}
    for label, beta in (("no_effect", 0.0), ("planted_effect_0.8", 0.8)):
        ers, skills, true_sel = [], [], 0
        for _ in range(n):
            eff = [("caffeine", "sleep_quality", 1, beta)] if beta else []
            p = simulate_panel(rng, T=total, names=names, ar=0.5, weekly=0.5, trend=0.2, missing=0.10, effects=eff)
            tr = p.slice(0, train)
            res = analyze_panel(tr, DEFAULT_CONFIG)
            if not res.candidates:
                continue
            best = min(res.candidates, key=lambda c: c["inference"]["p_combined"])   # model selected BY the data
            m = freeze_model(tr, best, DEFAULT_CONFIG)
            if m is None:
                continue
            sc = score_frozen(m, p, p.dates[train], p.dates[-1], DEFAULT_CONFIG)
            if sc["scored_days"] < 8:
                continue
            ers.append(sc["evidence_ratio"])
            skills.append(sc["skill"])
            true_sel += best["id"] == "caffeine->sleep_quality@1"
        e = np.array(ers)
        out[label] = {"replicates": int(len(e)), "selected_true_pair": true_sel / max(1, len(e)), "median_evidence_ratio": float(np.median(e)),
                      "p_er_ge_20": float(np.mean(e >= 20)), "p_er_ge_3": float(np.mean(e >= 3)), "p_er_le_0.1": float(np.mean(e <= 0.1)),
                      "median_skill": float(np.median(skills)), "unseen_days": total - train}
    return out


def timing_study() -> dict:
    """Wall-clock time of one full analysis for different numbers of logged variables (90 days, 10% missing)."""
    rng = np.random.default_rng(1)
    rows = []
    for k in (6, 8, 12, 24):
        names = [f"v{i}" for i in range(k)]
        p = simulate_panel(rng, T=90, names=names, ar=0.5, weekly=0.5, trend=0.2, missing=0.10, effects=[])
        t0 = time.time()
        res = analyze_panel(p, DEFAULT_CONFIG)
        rows.append({"variables": k, "candidates": len(res.candidates), "seconds": round(time.time() - t0, 2)})
    return {"rows": rows}


def run_extras(seed: int = 20261011, quick: bool = False) -> dict:
    t0 = time.time()
    out = {
        "experiment_size": experiment_size_study(300 if quick else 3000, seed + 5, [(14, 1, 0.0), (14, 1, 0.5), (14, 1, 0.8), (10, 2, 0.5), (8, 3, 0.5), (20, 1, 0.5)]),
        "spc": spc_study(150 if quick else 500, seed + 6),
        "forecast": forecast_study(40 if quick else 120, seed + 7),
        "timing": timing_study(),
    }
    out["seconds"] = round(time.time() - t0, 1)
    return out


def run(quick: bool, seed: int = 20261011) -> dict:
    t0 = time.time()
    s_null = [dict(T=60, ar=0.3, missing=0.10, weekly=0.5), dict(T=90, ar=0.5, missing=0.10, weekly=0.5),
              dict(T=90, ar=0.8, missing=0.15, weekly=0.5), dict(T=120, ar=0.5, missing=0.20, weekly=0.5, round_scale=True)]
    n_null = 80 if quick else 400
    n_mix = 48 if quick else 240
    out = {"engine": "NexGene Research Engine", "seed": seed, "quick": quick, "null": null_study(n_null, seed, s_null), "mixed": []}
    s_pair = [dict(T=60, ar=0.0, missing=0.10, weekly=0.6, trend=0.4), dict(T=60, ar=0.5, missing=0.10, weekly=0.6, trend=0.4),
              dict(T=60, ar=0.8, missing=0.10, weekly=0.6, trend=0.4), dict(T=90, ar=0.5, missing=0.20, weekly=0.6, trend=0.4, round_scale=True),
              dict(T=45, ar=0.6, missing=0.15, weekly=0.6, trend=0.4)]
    out["pairwise_calibration"] = pairwise_calibration_study(150 if quick else 600, seed + 1, s_pair)
    for T in (60, 90, 120):
        out["mixed"].append(mixed_study(n_mix, seed + T, dict(T=T, ar=0.5, missing=0.10, weekly=0.5, trend=0.2), strengths=(0.4, 0.7, 1.0, 1.4)))
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--quick", action="store_true")
    g.add_argument("--full", action="store_true")
    g.add_argument("--extras", action="store_true", help="randomisation-test size, forward-test, drift-detector and timing studies")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = run_extras(quick=False) if a.extras else run(quick=not a.full)
    text = json.dumps(res, indent=2)
    if a.out:
        open(a.out, "w").write(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
