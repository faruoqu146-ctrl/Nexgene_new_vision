"""Run the research engine on a CSV export, with no web stack or database.

    python -m backend.app.research.cli analyze data.csv --tz Africa/Lagos --out report.json --md report.md
    python -m backend.app.research.cli demo

CSV formats (header required)
  long: date,kind,value        (several rows per day are averaged)
  wide: date,<variable>,<variable>,...   (blank cells are missing, never zero)
``date`` may be YYYY-MM-DD or an ISO datetime.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional, Sequence

import numpy as np

from .config import EngineConfig, label
from .discovery import analyze_panel
from .narrative import build_brief
from .panel import panel_from_arrays


def _parse_day(text: str) -> date:
    text = text.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return datetime.fromisoformat(text).date()


def read_csv(path: str) -> dict:
    """Return {variable: {date: [values]}}."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError("CSV has no data rows")
    cols = [c.strip().lower() for c in rows[0].keys()]
    date_col = next((k for k in rows[0] if k.strip().lower() in ("date", "timestamp", "recorded_at")), None)
    if date_col is None:
        raise ValueError("CSV needs a 'date' column")
    series: dict = defaultdict(lambda: defaultdict(list))
    if "kind" in cols and "value" in cols:
        kcol = next(k for k in rows[0] if k.strip().lower() == "kind")
        vcol = next(k for k in rows[0] if k.strip().lower() == "value")
        for r in rows:
            if (r[vcol] or "").strip() == "":
                continue
            series[r[kcol].strip()][_parse_day(r[date_col])].append(float(r[vcol]))
    else:
        for r in rows:
            d = _parse_day(r[date_col])
            for k, v in r.items():
                if k == date_col or v is None or v.strip() == "":
                    continue
                series[k.strip()][d].append(float(v))
    return series


def panel_from_series(series: dict, window_days: int, end: Optional[date] = None):
    all_days = [d for v in series.values() for d in v]
    last = end or max(all_days)
    start = last - timedelta(days=window_days - 1)
    arrays = {}
    for name, per_day in series.items():
        arr = np.full(window_days, np.nan)
        for d, vals in per_day.items():
            i = (d - start).days
            if 0 <= i < window_days:
                arr[i] = float(np.mean(vals))
        arrays[name] = arr
    return panel_from_arrays(arrays, start)


def render_markdown(result, brief: dict) -> str:
    out = ["# NexGene Research Engine report", "",
           f"Window: {result.manifest['window'].get('start')} to {result.manifest['window'].get('end')} "
           f"({result.manifest['window'].get('days')} days) - data quality {result.quality['score']}/100", ""]
    out += ["## Findings", ""]
    if not brief["findings"]:
        out += ["No relationship currently reaches an evidence level worth reporting.", ""]
    for f in brief["findings"]:
        out += [f"### {f['headline']}", f"*{f['tier']} - {f['tier_label']} - status {f['status']}*", "", f["effect"], "", f["evidence"], ""]
        out += [f"- {c}" for c in f["caveats"]] + [""]
    if brief["baseline_alerts"]:
        out += ["## Baseline changes", ""] + [f"- {a['message']}" for a in brief["baseline_alerts"]] + [""]
    if brief["next_experiments"]:
        out += ["## Suggested self-experiments", ""]
        for e in brief["next_experiments"]:
            days = e["days_needed"]
            out.append(f"- {label(e['exposure'])} -> {label(e['outcome'])}: {e['why']} "
                       f"{'About ' + str(days) + ' days needed.' if days else 'Not feasible at the expected effect size.'}")
        out.append("")
    out += ["## Evidence sufficiency", "", result.sufficiency.get("message", ""), "", "## Limitations", ""] + [f"- {s}" for s in brief["limitations"]]
    out += ["", "## Reproducibility", "", f"- run hash: `{result.manifest['run_hash']}`", f"- input hash: `{result.manifest['input_hash']}`",
            f"- engine: {result.manifest['model_version']} (code `{result.manifest['code_fingerprint'][:12]}`)"]
    return "\n".join(out) + "\n"


def _demo_panel():
    from .simulate import simulate_panel
    rng = np.random.default_rng(7)
    names = ["caffeine", "alcohol", "activity_duration", "mood", "energy", "focus", "stress", "sleep_quality"]
    return simulate_panel(rng, T=90, names=names, ar=0.5, weekly=0.4, trend=0.2, missing=0.1,
                          effects=[("activity_duration", "mood", 1, 1.4), ("stress", "focus", 0, -1.4)])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyse a CSV export")
    a.add_argument("csv")
    a.add_argument("--window", type=int, default=90)
    a.add_argument("--out", help="write full JSON results here")
    a.add_argument("--md", help="write a markdown report here")
    sub.add_parser("demo", help="analyse a synthetic example with planted effects")
    ns = ap.parse_args(argv)
    cfg = EngineConfig(window_days=getattr(ns, "window", 90))
    panel = panel_from_series(read_csv(ns.csv), cfg.window_days) if ns.cmd == "analyze" else _demo_panel()
    result = analyze_panel(panel, cfg)
    brief = build_brief(result)
    md = render_markdown(result, brief)
    if ns.cmd == "analyze" and ns.out:
        with open(ns.out, "w") as fh:
            json.dump(result.to_dict(), fh, indent=2)
    if ns.cmd == "analyze" and ns.md:
        with open(ns.md, "w") as fh:
            fh.write(md)
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
