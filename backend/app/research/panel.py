"""Daily longitudinal panel: timezone-correct aggregation, calendar grid, data quality.

Design rules
  * The panel is a regular calendar grid (one slot per local day). Missing days are
    NaN. Missing values are never imputed and never coerced to zero.
  * Naive datetimes (as returned by SQLite) are interpreted as UTC, never as the
    server's local time.
  * ``Panel.digest()`` hashes the canonical content so a run can be reproduced and
    verified byte-for-byte.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

import numpy as np

from .config import DEFAULT_CONFIG, SCALE_0_10, EngineConfig


@dataclass
class Panel:
    dates: list
    variables: dict
    sources: dict
    entry_counts: dict
    multi_entry_days: dict
    tz: str
    tz_fallback: bool
    window_start: date
    window_end: date

    @property
    def T(self) -> int:
        return len(self.dates)

    @property
    def ordinals(self) -> np.ndarray:
        return np.array([d.toordinal() for d in self.dates], dtype=np.int64)

    @property
    def weekdays(self) -> np.ndarray:
        return np.array([d.weekday() for d in self.dates], dtype=np.int64)

    def iso_weeks(self, mask: Optional[np.ndarray] = None) -> set:
        idx = range(self.T) if mask is None else np.flatnonzero(mask)
        return {self.dates[i].isocalendar()[:2] for i in idx}

    def observed_mask(self, name: str) -> np.ndarray:
        return ~np.isnan(self.variables[name])

    def any_observed_mask(self) -> np.ndarray:
        if not self.variables:
            return np.zeros(self.T, dtype=bool)
        return np.any(np.vstack([~np.isnan(v) for v in self.variables.values()]), axis=0)

    def digest(self) -> str:
        h = hashlib.sha256()
        h.update(f"{self.window_start.isoformat()}|{self.window_end.isoformat()}|{self.tz}".encode())
        for name in sorted(self.variables):
            v = self.variables[name]
            m = ~np.isnan(v)
            h.update(name.encode())
            h.update(m.astype("u1").tobytes())
            h.update(np.round(np.where(m, v, 0.0), 10).astype("<f8").tobytes())
        return h.hexdigest()

    def slice(self, start_idx: int, end_idx: int) -> "Panel":
        """Return a sub-panel [start_idx, end_idx) on the same grid."""
        return Panel(
            dates=self.dates[start_idx:end_idx],
            variables={k: v[start_idx:end_idx].copy() for k, v in self.variables.items()},
            sources=dict(self.sources), entry_counts=dict(self.entry_counts),
            multi_entry_days=dict(self.multi_entry_days), tz=self.tz, tz_fallback=self.tz_fallback,
            window_start=self.dates[start_idx], window_end=self.dates[end_idx - 1],
        )


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _resolve_tz(name: Optional[str]):
    """Return (tzinfo, fell_back). Falls back to UTC when the zone is unknown."""
    if not name or name.upper() == "UTC":
        return timezone.utc, False
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name), False
    except Exception:
        return timezone.utc, True


_SAFE = re.compile(r"[^a-z0-9_.\-]+")


def _bm_name(code: str) -> str:
    return "bm:" + _SAFE.sub("_", str(code).strip().lower())[:60]


def build_panel(
    observations: Iterable,
    *,
    tz: Optional[str] = "UTC",
    end: Optional[datetime] = None,
    window_days: int = 90,
    biomarkers: Optional[Iterable] = None,
) -> Panel:
    """Aggregate raw rows into a daily grid.

    ``observations`` need ``.kind``, ``.value_numeric`` and ``.recorded_at``.
    ``biomarkers`` need ``.marker_code``, ``.value_numeric``, ``.recorded_at`` and
    optionally ``.quality`` / ``.result_mode``; poor-quality signals are excluded.
    """
    tzinfo, fell_back = _resolve_tz(tz)
    end_dt = _as_utc(end) if end is not None else datetime.now(timezone.utc)
    end_day = end_dt.astimezone(tzinfo).date()
    start_day = end_day - timedelta(days=window_days - 1)
    T = window_days
    dates = [start_day + timedelta(days=i) for i in range(T)]

    sums: dict = defaultdict(lambda: np.zeros(T))
    cnts: dict = defaultdict(lambda: np.zeros(T, dtype=np.int64))
    sources: dict = {}
    entries: dict = defaultdict(int)

    def _add(name: str, value, recorded_at, source: str):
        if value is None or recorded_at is None:
            return
        v = float(value)
        if not math.isfinite(v):
            return
        day = _as_utc(recorded_at).astimezone(tzinfo).date()
        i = (day - start_day).days
        if i < 0 or i >= T:
            return
        sums[name][i] += v
        cnts[name][i] += 1
        sources[name] = source
        entries[name] += 1

    for r in observations:
        _add(str(r.kind), getattr(r, "value_numeric", None), getattr(r, "recorded_at", None), "observation")
    for b in (biomarkers or []):
        if getattr(b, "quality", "good") == "poor" or getattr(b, "result_mode", "quantitative") == "deviation":
            continue
        _add(_bm_name(b.marker_code), getattr(b, "value_numeric", None), getattr(b, "recorded_at", None), "biomarker")

    variables, multi = {}, {}
    for name in sorted(sums):
        c = cnts[name]
        arr = np.full(T, np.nan)
        m = c > 0
        arr[m] = sums[name][m] / c[m]
        variables[name] = arr
        multi[name] = int((c > 1).sum())
    return Panel(dates, variables, sources, dict(entries), multi, tz or "UTC", fell_back, start_day, end_day)


def panel_from_arrays(variables: dict, start: date, *, tz: str = "UTC") -> Panel:
    """Build a panel directly from equal-length arrays (tests, simulation, CSV)."""
    lengths = {len(v) for v in variables.values()}
    if len(lengths) != 1:
        raise ValueError("all variables must have the same length")
    T = lengths.pop()
    dates = [start + timedelta(days=i) for i in range(T)]
    vv = {k: np.asarray(v, dtype=float).copy() for k, v in sorted(variables.items())}
    return Panel(dates, vv, {k: "observation" for k in vv}, {k: int((~np.isnan(v)).sum()) for k, v in vv.items()},
                 {k: 0 for k in vv}, tz, False, dates[0], dates[-1])


# --------------------------------------------------------------------------- #
# Data quality
# --------------------------------------------------------------------------- #
def _longest_gap(mask: np.ndarray) -> int:
    best = run = 0
    for ok in mask:
        run = 0 if ok else run + 1
        best = max(best, run)
    return best


def _acf1(v: np.ndarray) -> Optional[float]:
    a, b = v[:-1], v[1:]
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 6:
        return None
    a, b = a[m] - a[m].mean(), b[m] - b[m].mean()
    den = math.sqrt(float(a @ a) * float(b @ b))
    return float(a @ b / den) if den > 0 else None


def variable_profile(name: str, v: np.ndarray, cfg: EngineConfig = DEFAULT_CONFIG, weekdays: Optional[np.ndarray] = None) -> dict:
    m = ~np.isnan(v)
    n = int(m.sum())
    out = {"name": name, "n_days": n, "coverage": round(n / len(v), 4) if len(v) else 0.0, "eligible": False, "reasons": []}
    if n == 0:
        out["reasons"].append("no_numeric_observations")
        return out
    x = v[m]
    vals, counts = np.unique(np.round(x, 6), return_counts=True)
    modal = float(counts.max() / n)
    out.update({
        "mean": float(x.mean()), "sd": float(x.std(ddof=1)) if n > 1 else 0.0,
        "min": float(x.min()), "max": float(x.max()), "n_distinct": int(len(vals)),
        "modal_share": round(modal, 4), "longest_gap_days": _longest_gap(m), "acf1": _acf1(v),
    })
    if name in SCALE_0_10:
        out["floor_share"] = round(float((x <= 0.0 + 1e-9).mean()), 4)
        out["ceiling_share"] = round(float((x >= 10.0 - 1e-9).mean()), 4)
    if weekdays is not None:
        out["weekday_counts"] = [int((m & (weekdays == k)).sum()) for k in range(7)]
    reasons = out["reasons"]
    if n < cfg.min_obs_days:
        reasons.append("too_few_observed_days")
    if len(vals) < cfg.min_distinct_values:
        reasons.append("too_few_distinct_values")
    if modal > cfg.max_modal_share:
        reasons.append("near_constant_or_straight_lined")
    if out["sd"] == 0.0:
        reasons.append("zero_variance")
    out["eligible"] = not reasons
    return out


def panel_quality(panel: Panel, cfg: EngineConfig = DEFAULT_CONFIG) -> dict:
    wd = panel.weekdays
    profiles = {name: variable_profile(name, v, cfg, wd) for name, v in panel.variables.items()}
    eligible = [p for p in profiles.values() if p["eligible"]]
    active_days = int(panel.any_observed_mask().sum())
    if eligible:
        cov = float(np.mean([min(1.0, p["coverage"] / 0.8) for p in eligible]))
        reg = 1.0 - float(np.mean([min(1.0, p["longest_gap_days"] / 14.0) for p in eligible]))
        var = float(np.mean([1.0 if (p["modal_share"] <= cfg.max_modal_share and p["n_distinct"] >= 4) else 0.0 for p in eligible]))
        breadth = min(1.0, len(eligible) / 6.0)
    else:
        cov = reg = var = breadth = 0.0
    depth = min(1.0, active_days / 42.0)
    score = 100.0 * (0.35 * cov + 0.20 * reg + 0.20 * var + 0.15 * breadth + 0.10 * depth)
    warnings = []
    if panel.tz_fallback:
        warnings.append("timezone_unresolved_utc_day_boundaries_used")
    for p in profiles.values():
        if "near_constant_or_straight_lined" in p["reasons"]:
            warnings.append(f"{p['name']}:near_constant_values_limit_inference")
        if p.get("ceiling_share", 0) > 0.4 or p.get("floor_share", 0) > 0.4:
            warnings.append(f"{p['name']}:ceiling_or_floor_effects")
    for name, k in panel.multi_entry_days.items():
        if k > 0:
            warnings.append(f"{name}:{k}_days_with_multiple_entries_were_averaged")
    return {
        "score": round(score, 1),
        "components": {"coverage": round(cov, 3), "regularity": round(reg, 3), "variability": round(var, 3),
                       "breadth": round(breadth, 3), "depth": round(depth, 3)},
        "window_days": panel.T, "active_days": active_days, "active_weeks": len(panel.iso_weeks(panel.any_observed_mask())),
        "eligible_variables": sorted(p["name"] for p in eligible),
        "ineligible_variables": {p["name"]: p["reasons"] for p in profiles.values() if not p["eligible"]},
        "variables": profiles, "warnings": sorted(set(warnings)),
        "note": "Quality score is a transparent heuristic, not a validated instrument.",
    }
