"""Engine configuration and variable taxonomy (boot-safe)."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Optional

ENGINE_NAME = "NexGene Research Engine"
ENGINE_VERSION = "0.4.0"
MODEL_VERSION = "nre-0.4.0-research-core"

ERL = {0: "insufficient", 1: "hypothesis", 2: "candidate", 3: "supported", 4: "confirmed", 5: "experimental"}
ALL_STATUSES = {"TESTING", "SUPPORTED", "CONFIRMED", "REJECTED", "INCONCLUSIVE", "ARCHIVED"}

LABELS = {
    "sleep_duration": ("sleep duration", "hours"),
    "sleep_quality": ("sleep quality", "points (0-10)"),
    "energy": ("energy", "points (0-10)"),
    "mood": ("mood", "points (0-10)"),
    "stress": ("stress", "points (0-10)"),
    "focus": ("focus", "points (0-10)"),
    "activity_level": ("activity level", "points (0-10)"),
    "activity_duration": ("activity duration", "minutes"),
    "diet_quality": ("diet quality", "points (0-10)"),
    "caffeine": ("caffeine", "servings"),
    "alcohol": ("alcohol", "servings"),
    "nicotine": ("nicotine", "units"),
}


@dataclass(frozen=True)
class EngineConfig:
    window_days: int = 90
    min_days: int = 8
    min_pairs: int = 8
    max_hypotheses: int = 40
    alpha: float = 0.05
    fdr_q: float = 0.10
    seed: Optional[int] = 42
    lags: tuple = (0, 1)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lags"] = list(self.lags)
        return d


DEFAULT_CONFIG = EngineConfig()


def label(kind: str) -> str:
    return LABELS.get(kind, (kind.replace("_", " "), ""))[0]


def unit(kind: str) -> str:
    return LABELS.get(kind, ("", "units"))[1]
