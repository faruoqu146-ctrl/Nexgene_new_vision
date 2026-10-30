"""NexGene Research Engine.

A calibrated, auditable research core for personal longitudinal data. See
``docs/PHASE_12_RESEARCH_ENGINE.md`` for the methods and ``docs/PHASE_12_VALIDATION_REPORT.md``
for the measured operating characteristics.
"""
from .config import (  # noqa: F401
    ALL_STATUSES, DEFAULT_CONFIG, ENGINE_NAME, ENGINE_VERSION, ERL, MODEL_VERSION, EngineConfig, label, unit,
)
from .discovery import LIMITATIONS, ResearchResult, analyze_panel  # noqa: F401
from .experiment import (  # noqa: F401
    analyze_experiment, design_experiment, design_power, expected_direction_from_observation,
    verify_preregistration as verify_experiment_preregistration,
)
from .forecast import (  # noqa: F401
    freeze_model, horizon_verdict, preregistration, score_frozen, summarize_track,
    verify_preregistration as verify_forecast_preregistration,
)
from .narrative import (  # noqa: F401
    alternatives_for, build_brief, describe_candidate, next_experiments, prediction_text, rationale_for,
)
from .panel import Panel, build_panel, panel_from_arrays, panel_quality  # noqa: F401
from .provenance import canonical_json, code_fingerprint, to_jsonable, verify_chain  # noqa: F401


def run_research(observations, *, tz="UTC", end=None, biomarkers=None, config: EngineConfig = DEFAULT_CONFIG, **kwargs):
    """Convenience: build a panel from raw rows and analyse it."""
    panel = build_panel(observations, tz=tz, end=end, window_days=config.window_days, biomarkers=biomarkers)
    return panel, analyze_panel(panel, config, **kwargs)
