"""Synthetic observations (boot-safe)."""
from __future__ import annotations
import random
from datetime import datetime, timedelta, timezone
from typing import List, Optional

def synthetic_observations(days: int = 30, *, seed: int = 42, kinds: Optional[List[str]] = None, start=None):
    rng = random.Random(seed)
    kinds = kinds or ["sleep_duration", "mood", "focus", "stress", "energy"]
    end = start or datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    rows = []
    for d in range(days):
        day = end - timedelta(days=(days - 1 - d))
        for k in kinds:
            val = rng.uniform(5.5, 8.5) if k == "sleep_duration" else rng.uniform(3.0, 9.0)
            rows.append({"kind": k, "value_numeric": round(val, 2), "value_text": None, "observed_at": day, "recorded_at": day})
    return rows
