"""Check-in value rules (single source of truth, no third-party imports).

Why this module exists
----------------------
The mobile UI offers some evening questions as categorical choices (activity, eating, nicotine) and
sends caffeine / alcohol counts as digit strings ("1", "2", "3"). The API validator used to reject
every string for a numeric kind, so *any* evening check-in the UI could produce failed with HTTP 422
and the user never received feedback. These rules make the contract explicit:

* numeric kinds take finite numbers inside their range; numeric-looking strings from older cached
  clients ("2") are converted to numbers, anything else is rejected;
* three kinds are intentionally categorical and take a closed vocabulary (stored as text, never
  silently turned into numbers);
* "skipped" is a statement about the question, not an observation, and is dropped before storage.

Nothing here lowers a scientific threshold: no value is invented, and out-of-range numbers are still rejected.
"""
from __future__ import annotations

import math
from typing import Mapping

NUMERIC_OBSERVATION_RANGES = {
    "sleep_duration": (0.0, 24.0), "sleep_quality": (0.0, 10.0), "energy": (0.0, 10.0),
    "mood": (0.0, 10.0), "stress": (0.0, 10.0), "focus": (0.0, 10.0),
    "activity_level": (0.0, 10.0), "activity_duration": (0.0, 1440.0), "diet_quality": (0.0, 10.0),
    "caffeine": (0.0, 20.0), "alcohol": (0.0, 20.0), "nicotine": (0.0, 100.0),
    "weight": (20.0, 500.0), "heart_rate": (20.0, 250.0), "hrv": (0.0, 1000.0),
    "blood_pressure_systolic": (50.0, 300.0), "blood_pressure_diastolic": (30.0, 200.0),
    "glucose": (20.0, 1000.0), "temperature": (25.0, 45.0),
}

ALLOWED_OBSERVATIONS = {
    "sleep_duration", "sleep_quality", "energy", "mood", "stress", "focus",
    "activity_level", "activity_duration", "morning_context", "diet_quality",
    "caffeine", "alcohol", "nicotine", "weight", "heart_rate", "hrv",
    "blood_pressure_systolic", "blood_pressure_diastolic", "glucose", "temperature",
}

# Kinds the UI asks as categories. They stay text; the research engine treats them as non-numeric.
CATEGORICAL_VOCABULARY = {
    "activity_level": frozenset({"very_little", "light", "moderate", "high"}),
    "diet_quality": frozenset({"low", "fair", "mixed", "good", "high"}),
    "nicotine": frozenset({"none", "some", "frequent"}),
}
SKIPPED = "skipped"

# Which questionnaire a kind belongs to. Observations carry no period column, so period is derived from the kind.
MORNING_CORE = ("sleep_duration", "sleep_quality", "energy")
MORNING_OPTIONAL = ("morning_context",)
EVENING_CORE = ("mood", "stress", "focus")
EVENING_OPTIONAL = ("activity_level", "diet_quality", "caffeine", "alcohol", "nicotine")
PERIOD_KINDS = {
    "morning": MORNING_CORE + MORNING_OPTIONAL,
    "evening": EVENING_CORE + EVENING_OPTIONAL,
}


class CheckinValueError(ValueError):
    """A submitted value violates the check-in contract. ``kind`` names the offending question."""

    def __init__(self, message: str, kind: str | None = None):
        super().__init__(message)
        self.kind = kind


def _as_finite_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def normalize_values(values: Mapping[str, object], *, max_keys: int, max_text: int) -> dict:
    """Validate and normalise a check-in payload. Returns a new dict; raises :class:`CheckinValueError`.

    Skipped answers are removed (a skip is not an observation). A payload made only of skips is not an
    error here; it normalises to an empty dict and the caller stores zero rows.
    """
    if len(values) > max_keys:
        raise CheckinValueError(f"A check-in may contain at most {max_keys} values")
    out: dict = {}
    for kind, value in values.items():
        if not isinstance(kind, str) or len(kind) > 80:
            raise CheckinValueError("Invalid observation kind")
        if kind not in ALLOWED_OBSERVATIONS:
            raise CheckinValueError("Unsupported observation kind", kind)
        if isinstance(value, str) and len(value) > max_text:
            raise CheckinValueError("Observation value is too long", kind)
        if isinstance(value, str) and value.strip().lower() == SKIPPED:
            continue  # not an observation
        if kind in NUMERIC_OBSERVATION_RANGES:
            vocab = CATEGORICAL_VOCABULARY.get(kind)
            if isinstance(value, str) and vocab and value in vocab:
                out[kind] = value
                continue
            number = _as_finite_number(value)
            if number is None:
                raise CheckinValueError(
                    f"{kind} needs a number" + (" or one of its listed choices" if vocab else ""), kind)
            lo, hi = NUMERIC_OBSERVATION_RANGES[kind]
            if number < lo or number > hi:
                raise CheckinValueError(f"Observation value for {kind} is outside the allowed range", kind)
            out[kind] = number
        else:
            if not isinstance(value, str):
                number = _as_finite_number(value)
                if number is None:
                    raise CheckinValueError("Observation value must be finite", kind)
                out[kind] = number
            else:
                out[kind] = value
    return out
