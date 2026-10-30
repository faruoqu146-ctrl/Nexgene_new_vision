"""Lightweight synthetic panel helpers for tests and demos."""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import List


def synthetic_observations(
    days: int = 30,
    *,
    seed: int = 42,
    kinds: List[str] | None = None,
    start: datetime | None = None,
) -> list[dict]:
    """Return a list of observation dicts with observed_at in UTC."""
    rng = random.Random(seed)
    kinds = kinds or ["sleep_duration", "mood", "focus", "stress", "energy"]
    end = start or datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    rows = []
    for d in range(days):
        day = end - timedelta(days=(days - 1 - d))
        for k in kinds:
            if k == "sleep_duration":
                val = rng.uniform(5.5, 8.5)
            else:
                val = rng.uniform(3.0, 9.0)
            rows.append({
                "kind": k,
                "value_numeric": round(val, 2),
                "value_text": None,
                "observed_at": day,
                "recorded_at": day,
            })
    return rows
