"""Pre-registered randomised self-experiments (N-of-1 crossover) with exact inference.

An observational scan can only ever say that two things move together. A self-
experiment assigns the exposure by a pre-committed random schedule, which is the
only route to evidence about what a change does *for this person*.

Design
  * Blocks of two equal periods; the order of "usual" (A) and "intervention" (B)
    within each block is randomised. Randomisation bits come from SHA-256 of
    (seed, block), so a schedule is exactly reproducible on any machine.
  * The outcome for an assignment day is read ``lag`` days later; optional washout
    days at the start of each period are excluded from the analysis.
  * The analysis plan (primary outcome, test, alpha, adherence rule) is hashed
    BEFORE any data exist, and effect estimates are withheld until the schedule is
    complete, which prevents optional stopping and outcome peeking.

Analysis
  * Primary: intention-to-treat mean of within-block differences (B - A) with an
    exact sign-flip randomisation test and a randomisation-inversion 95% interval.
  * Manipulation check: the same test applied to the logged exposure.
  * Secondary: complier effect (Wald ratio) when the manipulation check passes.
  * Bayesian posterior for the effect under a weakly informative prior.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta
from typing import Optional

import numpy as np

from .config import LOW_CONTROLLABILITY, RANDOMIZABLE_EXPOSURES
from .panel import Panel
from .provenance import canonical_json, sha256_hex
from .special import norm_cdf, t_ppf

PROTOCOL = "nexgene-n1-randomised-crossover-v1"
EXACT_MAX_BLOCKS = 16
MC_DRAWS = 20000
ALPHA = 0.05
ADHERENCE_P = 0.10
MIN_VALID_BLOCKS = 6


# --------------------------------------------------------------------------- #
# Design
# --------------------------------------------------------------------------- #
def _first_is_b(seed: int, block: int) -> bool:
    return bool(hashlib.sha256(f"{PROTOCOL}:{seed}:{block}".encode()).digest()[0] & 1)


def expected_direction_from_observation(r_sign: int, intervention: str) -> str:
    """Outcome direction implied by an observed association sign and the intended change in exposure."""
    up = (r_sign > 0) == (intervention == "increase")
    return "higher" if up else "lower"


def design_power(*, outcome_sd: Optional[float], rho: Optional[float], n_blocks: int, period_len: int,
                 washout_days: int = 0, effect: Optional[float] = None) -> dict:
    """Minimum detectable effect (80% power, alpha .05) for the paired block design, and blocks needed for ``effect``."""
    if not outcome_sd or outcome_sd <= 0:
        return {"available": False, "reason": "outcome variability unknown"}
    rho = 0.0 if rho is None else min(0.9, max(0.0, rho))
    P = max(1, period_len - washout_days)

    def sigma_d(P_):
        var_mean = (outcome_sd ** 2 / P_) * (1.0 + 2.0 * sum((1 - h / P_) * rho ** h for h in range(1, P_)))
        return math.sqrt(2.0 * var_mean)

    def mde(nb):
        df = max(1, nb - 1)
        return (t_ppf(0.975, df) + t_ppf(0.80, df)) * sigma_d(P) / math.sqrt(nb)

    out = {"available": True, "outcome_sd": outcome_sd, "rho": rho, "analysis_days_per_period": P,
           "mde_80": mde(n_blocks), "mde_80_in_outcome_sd": mde(n_blocks) / outcome_sd}
    if effect and effect != 0:
        need = next((nb for nb in range(MIN_VALID_BLOCKS, 91) if mde(nb) <= abs(effect)), None)
        out["blocks_needed_for_effect"] = need
        out["days_needed_for_effect"] = None if need is None else need * 2 * period_len
        out["effect_used"] = abs(effect)
    return out


def design_experiment(*, exposure: str, outcome: str, start: date, seed: int, lag: int = 0, n_blocks: int = 14,
                      period_len: int = 1, washout_days: int = 0, intervention: str = "decrease",
                      expected_direction: Optional[str] = None, hypothesis_id: Optional[str] = None,
                      label_a: str = "usual", label_b: str = "intervention",
                      outcome_sd: Optional[float] = None, rho: Optional[float] = None,
                      expected_effect: Optional[float] = None) -> dict:
    if intervention not in ("increase", "decrease"):
        raise ValueError("intervention must be 'increase' or 'decrease'")
    if expected_direction not in (None, "higher", "lower"):
        raise ValueError("expected_direction must be 'higher', 'lower' or None")
    if not (MIN_VALID_BLOCKS <= n_blocks <= 60):
        raise ValueError(f"n_blocks must be between {MIN_VALID_BLOCKS} and 60")
    if not (1 <= period_len <= 7):
        raise ValueError("period_len must be between 1 and 7 days")
    if not (0 <= washout_days < period_len):
        raise ValueError("washout_days must be >= 0 and smaller than period_len")
    if not (0 <= lag <= 3):
        raise ValueError("lag must be between 0 and 3")
    if exposure == outcome:
        raise ValueError("exposure and outcome must differ")
    schedule = []
    for b in range(n_blocks):
        first_b = _first_is_b(seed, b)
        order = ("B", "A") if first_b else ("A", "B")
        for p_idx, cond in enumerate(order):
            for k in range(period_len):
                day = start + timedelta(days=b * 2 * period_len + p_idx * period_len + k)
                schedule.append({"date": day.isoformat(), "block": b, "period": p_idx, "condition": cond,
                                 "analysis_day": k >= washout_days})
    body = {
        "protocol": PROTOCOL, "exposure": exposure, "outcome": outcome, "lag": lag, "n_blocks": n_blocks,
        "period_len": period_len, "washout_days": washout_days, "intervention": intervention,
        "expected_direction": expected_direction, "label_a": label_a, "label_b": label_b,
        "start": start.isoformat(), "end": schedule[-1]["date"], "seed": int(seed), "hypothesis_id": hypothesis_id,
        "schedule": schedule,
        "analysis_plan": {
            "primary_outcome": outcome, "primary_statistic": "mean over blocks of (mean outcome on B days - mean outcome on A days)",
            "outcome_read_lag_days": lag, "test": "two-sided sign-flip randomisation test over blocks",
            "exact_when_blocks_at_most": EXACT_MAX_BLOCKS, "alpha": ALPHA,
            "interval": "randomisation-inversion 95% interval", "minimum_valid_blocks": MIN_VALID_BLOCKS,
            "manipulation_check": f"exposure differs between B and A in the intended direction (one-sided intent), randomisation p <= {ADHERENCE_P}",
            "estimates_withheld_until_schedule_complete": True,
            "supported_if": "p <= alpha, manipulation check passed, and effect in the pre-specified direction",
            "refuted_if": "90% interval lies inside +/-0.2 outcome SD (practically negligible) with manipulation check passed and >= 8 valid blocks",
        },
    }
    notes = []
    if exposure not in RANDOMIZABLE_EXPOSURES:
        notes.append("This exposure is not something a schedule can reliably assign; compliance may be poor.")
    if exposure in LOW_CONTROLLABILITY:
        notes.append("This exposure is only partly under your control; the manipulation check may fail.")
    if hypothesis_id is None:
        notes.append("Not linked to an existing hypothesis; the result will be recorded but will not change a hypothesis tier.")
    return {
        "preregistration": {**body, "hash": sha256_hex(canonical_json(body))},
        "power": design_power(outcome_sd=outcome_sd, rho=rho, n_blocks=n_blocks, period_len=period_len,
                              washout_days=washout_days, effect=expected_effect),
        "total_days": len(schedule), "notes": notes,
        "limitations": ["Cannot be blinded; expectation effects are possible.",
                        "Evidence applies to this person and this period only.",
                        "Carry-over beyond the washout is not modelled."],
    }


def verify_preregistration(prereg: dict) -> bool:
    body = {k: v for k, v in prereg.items() if k != "hash"}
    return sha256_hex(canonical_json(body)) == prereg.get("hash")


# --------------------------------------------------------------------------- #
# Randomisation inference
# --------------------------------------------------------------------------- #
def _sign_matrix(n: int, seed: int):
    if n <= EXACT_MAX_BLOCKS:
        S = ((np.arange(2 ** n)[:, None] >> np.arange(n)[None, :]) & 1) * 2.0 - 1.0
        return S, True
    rng = np.random.default_rng(np.random.SeedSequence([seed % (2 ** 32), n]))
    return rng.integers(0, 2, size=(MC_DRAWS, n)) * 2.0 - 1.0, False


def signflip_p(d: np.ndarray, seed: int, theta: float = 0.0) -> tuple:
    """Two-sided sign-flip randomisation p-value for mean(d - theta) = 0. Returns (p, exact)."""
    n = len(d)
    S, exact = _sign_matrix(n, seed)
    e = d - theta
    obs = abs(float(e.mean()))
    stats = np.abs(S @ e) / n
    if exact:
        return float(np.mean(stats >= obs - 1e-12)), True
    return float((1.0 + np.sum(stats >= obs - 1e-12)) / (1.0 + len(stats))), False


def randomisation_ci(d: np.ndarray, seed: int, alpha: float = ALPHA, k: float = 8.0, points: int = 321,
                     weights: Optional[np.ndarray] = None) -> Optional[tuple]:
    """Randomisation-inversion interval for a constant additive effect (hull of non-rejected values)."""
    n = len(d)
    S, exact = _sign_matrix(n, seed)
    w = np.ones(n) if weights is None else weights
    centre = float(d.mean())
    scale = max(float(np.std(d, ddof=1)) / math.sqrt(n), 1e-9) if n > 1 else 1e-9
    grid = np.linspace(centre - k * scale, centre + k * scale, points)
    Sd = S @ d
    Sw = S @ w
    obs = np.abs(d.mean() - grid * w.mean())
    stats = np.abs(Sd[:, None] - grid[None, :] * Sw[:, None]) / n
    if exact:
        p = (stats >= obs[None, :] - 1e-12).mean(axis=0)
    else:
        p = (1.0 + (stats >= obs[None, :] - 1e-12).sum(axis=0)) / (1.0 + len(S))
    ok = np.flatnonzero(p > alpha)
    if len(ok) == 0:
        return None
    step = grid[1] - grid[0]
    lo = grid[ok[0]] - (step if ok[0] > 0 else 0.0)
    hi = grid[ok[-1]] + (step if ok[-1] < points - 1 else 0.0)
    bounded = ok[0] > 0 and ok[-1] < points - 1
    return float(lo), float(hi), bool(bounded)


def _block_stats(sched: list, lag: int, yv: np.ndarray, xv: np.ndarray, idx_of: dict, today: date) -> dict:
    """Per-block B-A differences of the outcome (read at date+lag) and of the logged exposure."""
    blocks: dict = {}
    for s in sched:
        if not s["analysis_day"]:
            continue
        d = date.fromisoformat(s["date"])
        b = blocks.setdefault(s["block"], {"yA": [], "yB": [], "xA": [], "xB": []})
        i = idx_of.get(d)
        j = idx_of.get(d + timedelta(days=lag))
        if i is not None and not np.isnan(xv[i]):
            b["x" + s["condition"]].append(float(xv[i]))
        if j is not None and (d + timedelta(days=lag)) <= today and not np.isnan(yv[j]):
            b["y" + s["condition"]].append(float(yv[j]))
    dy, dx, bid_y, bid_x, pair = [], [], [], [], []
    for b, v in sorted(blocks.items()):
        ok_y = bool(v["yA"]) and bool(v["yB"])
        ok_x = bool(v["xA"]) and bool(v["xB"])
        if ok_y:
            dy.append(np.mean(v["yB"]) - np.mean(v["yA"]))
            bid_y.append(b)
        if ok_x:
            dx.append(np.mean(v["xB"]) - np.mean(v["xA"]))
            bid_x.append(b)
        if ok_y and ok_x:
            pair.append((b, dy[-1], dx[-1]))
    return {"dy": np.array(dy), "dx": np.array(dx), "bid_y": bid_y, "bid_x": bid_x, "paired": pair, "blocks": blocks}


def analyze_experiment(prereg: dict, panel: Panel, today: date) -> dict:
    """Analyse an experiment. Before the schedule is complete only progress is returned."""
    if not verify_preregistration(prereg):
        return {"status": "INVALID", "reason": "pre-registration hash does not match its contents"}
    sched, lag = prereg["schedule"], prereg["lag"]
    yv, xv = panel.variables.get(prereg["outcome"]), panel.variables.get(prereg["exposure"])
    if yv is None or xv is None:
        return {"status": "NO_DATA", "reason": "outcome or exposure has no logged data in the analysis window"}
    idx_of = {d: i for i, d in enumerate(panel.dates)}
    first = date.fromisoformat(sched[0]["date"])
    last_outcome_day = date.fromisoformat(sched[-1]["date"]) + timedelta(days=lag)
    if first < panel.dates[0]:
        return {"status": "NO_DATA", "reason": "experiment started before the analysis window; widen the window"}
    bs = _block_stats(sched, lag, yv, xv, idx_of, today)
    n_blocks = prereg["n_blocks"]
    complete = today >= last_outcome_day
    assigned_days = sum(1 for s in sched if date.fromisoformat(s["date"]) <= today)
    x_a = [v for b in bs["blocks"].values() for v in b["xA"]]
    x_b = [v for b in bs["blocks"].values() for v in b["xB"]]
    progress = {
        "status": "COMPLETE_SCHEDULE" if complete else "IN_PROGRESS", "days_elapsed": assigned_days,
        "days_total": len(sched), "blocks_with_outcome_data": len(bs["dy"]), "blocks_total": n_blocks,
        "exposure_logged_days": {"A": len(x_a), "B": len(x_b)},
        "exposure_mean_so_far": {"A": float(np.mean(x_a)) if x_a else None, "B": float(np.mean(x_b)) if x_b else None},
        "estimates_withheld": not complete,
    }
    if not complete:
        progress["note"] = "Effect estimates are withheld until the pre-registered schedule is complete."
        return progress

    seed = prereg["seed"]
    dy = bs["dy"]
    out = dict(progress)
    out["estimates_withheld"] = False
    out["valid_blocks"] = int(len(dy))
    if len(dy) < MIN_VALID_BLOCKS:
        out.update({"verdict": "INCONCLUSIVE", "reason": f"only {len(dy)} blocks have outcome data in both arms (need {MIN_VALID_BLOCKS})"})
        return out

    p_itt, exact = signflip_p(dy, seed)
    ci = randomisation_ci(dy, seed)
    effect = float(dy.mean())
    outc = np.array([float(yv[idx_of[date.fromisoformat(s['date'])] + lag]) for s in sched
                     if s["analysis_day"] and (date.fromisoformat(s["date"]) + timedelta(days=lag)) in idx_of
                     and not np.isnan(yv[idx_of[date.fromisoformat(s['date'])] + lag])])
    sd_y = float(outc.std(ddof=1)) if len(outc) > 2 else float("nan")
    out["itt"] = {"effect": effect, "ci95": None if ci is None else [ci[0], ci[1]], "ci_bounded": None if ci is None else ci[2],
                  "p_randomisation": p_itt, "p_is_exact": exact, "block_differences": [float(v) for v in dy],
                  "effect_in_outcome_sd": effect / sd_y if sd_y and sd_y > 0 else None, "outcome_sd": sd_y}

    # manipulation check on the logged exposure
    dx = bs["dx"]
    intended = -1.0 if prereg["intervention"] == "decrease" else 1.0
    if len(dx) >= MIN_VALID_BLOCKS:
        p_x, _ = signflip_p(dx, seed + 1)
        eff_x = float(dx.mean())
        right_way = eff_x * intended > 0
        frac = float(np.mean(dx * intended > 0))
        adherence_ok = bool(right_way and p_x <= ADHERENCE_P)
        out["manipulation_check"] = {"exposure_effect": eff_x, "p_randomisation": p_x, "intended_direction_met": bool(right_way),
                                     "blocks_in_intended_direction": frac, "passed": adherence_ok}
    else:
        adherence_ok = False
        out["manipulation_check"] = {"passed": False, "reason": f"exposure logged in both arms for only {len(dx)} blocks"}

    # complier effect (Wald ratio) with randomisation-inversion interval, secondary
    cace = None
    if adherence_ok:
        pair = bs["paired"]
        if len(pair) >= MIN_VALID_BLOCKS:
            py_, px_ = np.array([p[1] for p in pair]), np.array([p[2] for p in pair])
            denom = float(px_.mean())
            if abs(denom) > 1e-9:
                theta = float(py_.mean()) / denom
                grid = np.linspace(theta - 6 * abs(theta) - 3 * float(py_.std(ddof=1) / max(abs(denom), 1e-9)),
                                   theta + 6 * abs(theta) + 3 * float(py_.std(ddof=1) / max(abs(denom), 1e-9)), 401)
                S, ex = _sign_matrix(len(py_), seed + 2)
                keep = []
                for th in grid:
                    e = py_ - th * px_
                    obs = abs(e.mean())
                    stats = np.abs(S @ e) / len(e)
                    pv = float(np.mean(stats >= obs - 1e-12)) if ex else float((1 + np.sum(stats >= obs - 1e-12)) / (1 + len(S)))
                    if pv > ALPHA:
                        keep.append(th)
                bounded = bool(keep) and keep[0] > grid[0] and keep[-1] < grid[-1]
                cace = {"effect_per_exposure_unit": theta, "ci95": [float(min(keep)), float(max(keep))] if keep and bounded else None,
                        "ci_bounded": bounded, "label": "secondary: effect per unit change in exposure among days the schedule actually moved exposure"}
    out["complier_effect"] = cace

    # Bayesian posterior for the ITT effect (weakly informative prior: N(0, (0.5 outcome SD)^2))
    n = len(dy)
    se = float(dy.std(ddof=1)) / math.sqrt(n) if n > 1 else float("nan")
    if sd_y and sd_y > 0 and se and se > 0:
        tau = 0.5 * sd_y
        w = tau * tau / (tau * tau + se * se)
        mu, sd = w * effect, math.sqrt(w) * se
        rope = 0.2 * sd_y
        p_hi = 1.0 - norm_cdf((0.0 - mu) / sd)
        p_rope = norm_cdf((rope - mu) / sd) - norm_cdf((-rope - mu) / sd)
        out["bayes"] = {"posterior_mean": mu, "posterior_sd": sd, "p_effect_positive": p_hi, "p_effect_negligible": p_rope,
                        "rope_half_width": rope, "prior": "Normal(0, (0.5 x outcome SD)^2)"}

    # verdict according to the pre-registered rules
    direction = prereg.get("expected_direction")
    sig = p_itt <= ALPHA
    sign_ok = None if direction is None else ((effect > 0) == (direction == "higher"))
    verdict, reason = "INCONCLUSIVE", "No pre-registered rule was satisfied."
    if not adherence_ok:
        verdict, reason = "INCONCLUSIVE", "The manipulation check failed: the schedule did not move the exposure as intended, so the outcome comparison cannot be interpreted."
    elif sig and (sign_ok is True or direction is None):
        verdict, reason = "SUPPORTED", "Randomisation p <= 0.05 with the effect in the pre-specified direction and the manipulation check passed."
    elif sig and sign_ok is False:
        verdict, reason = "CONTRADICTED", "A significant effect in the opposite direction to the pre-specified one."
    elif ci is not None and ci[2] and len(dy) >= 8 and sd_y == sd_y and sd_y > 0:
        z90 = t_ppf(0.95, max(1, n - 1)) * se
        if abs(effect) + z90 < 0.2 * sd_y:
            verdict, reason = "REFUTED", "The effect is practically negligible: its 90% interval lies within +/-0.2 outcome SD."
    out["verdict"], out["verdict_reason"] = verdict, reason
    out["design_hash"] = prereg["hash"]
    return out
