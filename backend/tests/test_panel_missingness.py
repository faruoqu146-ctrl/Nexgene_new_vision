"""Missing values must not be coerced to zero in panel construction."""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from backend.app.research.panel import build_panel


class _Obs:
    def __init__(self, kind, value, recorded_at):
        self.kind = kind
        self.value_numeric = value
        self.recorded_at = recorded_at


def test_missing_days_are_nan_not_zero():
    end = datetime(2026, 10, 20, tzinfo=timezone.utc)
    obs = [
        _Obs("energy", 7.0, end - timedelta(days=9)),
        _Obs("energy", 6.0, end - timedelta(days=5)),
        _Obs("energy", 8.0, end - timedelta(days=1)),
    ]
    panel = build_panel(obs, tz="UTC", end=end, window_days=10)
    assert "energy" in panel.variables
    series = panel.variables["energy"]
    assert series.shape[0] == 10
    n_obs = int(np.sum(~np.isnan(series)))
    n_miss = int(np.sum(np.isnan(series)))
    assert n_obs == 3
    assert n_miss == 7
    finite = series[~np.isnan(series)]
    assert set(np.round(finite, 1).tolist()) == {6.0, 7.0, 8.0}
