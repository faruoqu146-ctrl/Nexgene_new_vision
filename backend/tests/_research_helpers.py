"""Shared helpers for the research-engine tests (imported by test modules; not collected as tests)."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from backend.app.research.simulate import simulate_panel  # noqa: E402

BEHAVIOR_AND_STATE = ["caffeine", "alcohol", "activity_duration", "mood", "energy", "focus", "stress", "sleep_quality"]


def planted_panel(seed=7, T=90, missing=0.10, effects=None, names=None, ar=0.5, round_scale=False):
    rng = np.random.default_rng(seed)
    names = names or BEHAVIOR_AND_STATE
    if effects is None:
        effects = [("activity_duration", "mood", 1, 1.4), ("stress", "focus", 0, -1.4)]
    return simulate_panel(rng, T=T, names=names, ar=ar, weekly=0.4, trend=0.2, missing=missing, effects=effects, round_scale=round_scale)


def null_panel(seed=3, T=90, missing=0.10, names=None):
    return planted_panel(seed=seed, T=T, missing=missing, effects=[], names=names)


def obs(kind, value, when):
    return SimpleNamespace(kind=kind, value_numeric=value, recorded_at=when)


def utc(y, m, d, h=12, mi=0, naive=False):
    dt = datetime(y, m, d, h, mi, tzinfo=timezone.utc)
    return dt.replace(tzinfo=None) if naive else dt
