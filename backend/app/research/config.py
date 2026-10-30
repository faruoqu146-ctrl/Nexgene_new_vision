"""Engine configuration, versioning, and the (non-medical) variable taxonomy.

Everything that changes an analytical result lives in :class:`EngineConfig`, so
a run is fully described by (input data hash, config hash, engine version, seed).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Optional

ENGINE_NAME = "nexgene.research"
ENGINE_VERSION = "1.2.0"
MODEL_VERSION = f"{ENGINE_NAME}/{ENGINE_VERSION}"

# Evidence-ranking ladder (ERL). Higher is stronger. Labels are non-clinical.
ERL = {
    0: "insufficient",
    1: "hypothesis",
    2: "candidate",
    3: "supported",
    4: "confirmed",
    5: "experimental",
}

ALL_STATUSES = {"TESTING", "SUPPORTED", "CONFIRMED", "REJECTED", "INCONCLUSIVE", "ARCHIVED"}

# Default units / display labels for known observation kinds (non-exhaustive).
_LABELS = {
    "sleep_duration": ("Sleep duration", "h"),
    "sleep_quality": ("Sleep quality", "/10"),
    "energy": ("Energy", "/10"),
    "mood": ("Mood", "/10"),
    "stress": ("Stress", "/10"),
    "focus": ("Focus", "/10"),
    "activity_level": ("Activity", "/10"),
    "activity_duration": ("Activity duration", "min"),
    "diet_quality": ("Diet quality", "/10"),
    "caffeine": ("Caffeine", "servings"),
    "alcohol": ("Alcohol", "servings"),
    "nicotine": ("Nicotine", "relative"),
    "weight": ("Weight", "kg"),
    "heart_rate": ("Heart rate", "bpm"),
    "hrv": ("HRV", "ms"),
    "blood_pressure_systolic": ("Systolic BP", "mmHg"),
    "blood_pressure_diastolic": ("Diastolic BP", "mmHg"),
    "glucose": ("Glucose", "mg/dL"),
    "temperature": ("Temperature", "°C"),
}


def label(kind: str) -> str:
    return _LABELS.get(kind, (kind.replace("_", " ").title(), ""))[0]


def unit(kind: str) -> str:
    return _LABELS.get(kind, (kind, ""))[1]


@dataclass(frozen=True)
class EngineConfig:
    """All knobs that can change an analytical result.

    Frozen so a config can be hashed and attached to a run without mutation risk.
    """

    window_days: int = 90
    min_days: int = 8
    min_pairs: int = 8
    max_hypotheses: int = 40
    alpha: float = 0.05
    fdr_q: float = 0.10
    seed: int = 42
    # discovery / association
    min_effect: float = 0.15
    rank_by: str = "stability"
    # forecasting
    forecast_horizon_days: int = 7
    # experiment design
    target_power: float = 0.8
    # narrative
    max_brief_items: int = 8
    extra: dict = field(default_factory=dict)

    def with_updates(self, **kwargs) -> "EngineConfig":
        return replace(self, **kwargs)

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CONFIG = EngineConfig()
