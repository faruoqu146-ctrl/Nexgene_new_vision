"""Engine configuration, versioning, and the (non-medical) variable taxonomy.

Everything that changes an analytical result lives in :class:`EngineConfig`, so
a run is fully described by (input data hash, config hash, engine version, seed).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Optional

ENGINE_NAME = "NexGene Research Engine"
ENGINE_VERSION = "0.4.0"
MODEL_VERSION = "nre-0.4.0-research-core"

# --------------------------------------------------------------------------- #
# Variable taxonomy. This is a *product* taxonomy (which signals a person can
# deliberately change vs. which are states to be explained). It makes no medical
# claim and is used only to (a) define the pre-specified hypothesis family and
# (b) decide which exposures can be randomised in a self-experiment.
# --------------------------------------------------------------------------- #
BEHAVIOR_EXPOSURES = frozenset({
    "caffeine", "alcohol", "nicotine", "activity_level", "activity_duration",
    "diet_quality", "sleep_duration",
})
STATE_OUTCOMES = frozenset({
    "sleep_quality", "energy", "mood", "stress", "focus", "hrv", "heart_rate",
    "blood_pressure_systolic", "blood_pressure_diastolic", "glucose",
    "temperature", "weight",
})
# Exposures that can realistically be assigned by a schedule (self-experiment).
RANDOMIZABLE_EXPOSURES = frozenset({
    "caffeine", "alcohol", "nicotine", "activity_level", "activity_duration",
    "diet_quality", "sleep_duration",
})
# Lower controllability: compliance is harder to guarantee.
LOW_CONTROLLABILITY = frozenset({"sleep_duration", "diet_quality"})

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
    "weight": ("weight", "kg"),
    "heart_rate": ("heart rate", "bpm"),
    "hrv": ("heart-rate variability", "ms"),
    "blood_pressure_systolic": ("systolic blood pressure", "mmHg"),
    "blood_pressure_diastolic": ("diastolic blood pressure", "mmHg"),
    "glucose": ("glucose", "mg/dL"),
    "temperature": ("body temperature", "deg C"),
}
SCALE_0_10 = frozenset({
    "sleep_quality", "energy", "mood", "stress", "focus", "activity_level", "diet_quality",
})

# Evidence Readiness Levels (ERL): a ladder that says what kind of claim the
# data can currently support. Only ERL-5 is interventional evidence.
ERL = {
    0: ("ERL-0", "Insufficient data", "The data cannot support any claim about this relationship yet."),
    1: ("ERL-1", "Exploratory signal", "A nominal signal that is still consistent with chance after accounting for multiple testing."),
    2: ("ERL-2", "Robust association", "Survives false-discovery control and robustness checks; observational, no direction implied."),
    3: ("ERL-3", "Temporally ordered association", "Exposure precedes outcome and adds predictive information beyond the outcome's own history; still observational."),
    4: ("ERL-4", "Prospectively confirmed", "A locked model predicted new, unseen days better than a no-effect model."),
    5: ("ERL-5", "Experimentally supported", "Supported by a pre-registered randomised self-experiment (N-of-1)."),
}

STATUS_BY_TIER = {0: "INCONCLUSIVE", 1: "TESTING", 2: "SUPPORTED", 3: "SUPPORTED", 4: "CONFIRMED", 5: "CONFIRMED"}
ALL_STATUSES = (
    "GENERATED", "SCREENING", "TESTABLE", "TESTING", "SUPPORTED", "CONFIRMED",
    "WEAKENED", "FALSIFIED", "INCONCLUSIVE", "SUPERSEDED",
)


@dataclass(frozen=True)
class EngineConfig:
    # --- data window / eligibility
    window_days: int = 90
    min_obs_days: int = 10               # a variable needs this many observed days
    min_distinct_values: int = 3
    max_modal_share: float = 0.85        # straight-lining guard
    # --- candidate generation
    lags: tuple = (0, 1, 2)
    min_pairs: int = 14                  # minimum overlapping days to test at all
    min_pairs_support: int = 21          # minimum for ERL >= 2
    min_active_weeks: int = 3
    max_pair_missingness: float = 0.65   # of expected pair-days, for ERL >= 2
    max_variables: int = 24              # keeps the quadratic candidate family (and request time) bounded
    max_candidates: int = 4000
    # --- inference
    shift_buffer: int = 3                # exclude circular shifts this close to the observed alignment
    min_shifts: int = 20
    null_acf_max_lag: int = 10           # lags used to estimate the effective number of independent shifts
    use_hac: bool = True
    # --- directional (temporal-order) gate
    directional_alpha: float = 0.01      # forward AR-controlled test must be this strong ...
    reverse_alpha: float = 0.05          # ... and the reverse test must NOT reach this level (unless clearly weaker)
    # --- multiplicity / gating
    alpha_q: float = 0.05
    diag_q_threshold: float = 0.25       # run the expensive diagnostics when q <= this ...
    diag_p_threshold: float = 0.05       # ... or when the combined p <= this
    max_diagnostic_candidates: int = 120
    effect_floor_r: float = 0.20         # practical floor on |adjusted r| for ERL >= 2
    rope_r: float = 0.10                 # region of practical equivalence on r
    # --- robustness
    bootstrap_resamples: int = 1000
    bootstrap_ci_level: float = 0.90
    winsor_q: float = 0.05
    highpass_window: int = 15
    # --- Bayesian layer
    bayes_prior_sd_z: float = 0.30       # default effect scale (Fisher-z) for Bayes factors
    # --- forward testing
    forecast_horizon_days: int = 14
    forecast_min_scored_days: int = 5
    forecast_informative_sd: float = 0.5
    evidence_ratio_confirm: float = 20.0
    evidence_ratio_weaken: float = 0.1
    forecast_min_informative_days: int = 10
    # --- SPC / drift
    drift_recent_days: int = 7
    drift_min_days: int = 14
    cusum_k: float = 0.5
    cusum_h: float = 5.0
    ewma_lambda: float = 0.2
    ewma_L: float = 3.0
    # --- reproducibility
    seed: Optional[int] = None           # None -> derived from the input-data hash

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lags"] = list(self.lags)
        return d

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()


DEFAULT_CONFIG = EngineConfig()


def label(kind: str) -> str:
    if kind in LABELS:
        return LABELS[kind][0]
    if kind.startswith("bm:"):
        return f"biomarker {kind[3:]}"
    return kind.replace("_", " ")


def unit(kind: str) -> str:
    return LABELS.get(kind, ("", "units"))[1]
