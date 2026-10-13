"""Simulation helpers for the research engine."""
from __future__ import annotations

import numpy as np
from typing import Optional, Tuple


def generate_panel(
    n_subjects: int = 50,
    n_time: int = 100,
    n_features: int = 10,
    seed: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Generate a simple panel dataset for testing.

    Returns (data, time, subject_ids).
    """
    rng = np.random.default_rng(seed)
    data = rng.normal(size=(n_subjects, n_time, n_features))
    time = np.arange(n_time, dtype=float)
    subjects = np.arange(n_subjects)
    return data, time, subjects
