# Phase 11: Dependence-aware inference and missingness diagnostics

## Implemented

- Circular-shift permutation sensitivity after weekday and linear-trend residualization for regular daily pairs with at least 12 observations.
- The shift test preserves the ordering of the residual series approximately while breaking its observed alignment with the other series. Shifts of one day in either direction are excluded to avoid near-identity null comparisons.
- When the permutation test is available, the engine uses the larger of the effective-N Student-t p-value and circular-shift p-value as a conservative combined p-value before Benjamini-Hochberg adjustment.
- Missingness diagnostics report expected pair-days, observed pair-days, pairwise missingness, exposure/outcome missingness, and longest consecutive pair gap. Missing values are not imputed as zero.
- Inference diagnostics record which p-values were used, enabling audit and comparison across model versions.

## Guardrails and limitations

- Permutation sensitivity is only calculated for regularly spaced daily pairs. Short or irregular series retain the effective-N Student-t result and explicitly mark permutation testing unavailable.
- Circular shifts are a sensitivity test under assumptions, not a general solution for all serial dependence, seasonality, time-varying confounding, or irregular observation processes.
- Missingness is described, not yet modeled as potentially informative. No automatic correction for missing-not-at-random data is claimed.
- The result remains observational association, not causation or diagnosis.

## Validation

Run `python -m pytest backend/tests/test_phase11_statistical_guards.py -q` for dependency-light statistical guard tests. The full app suite requires the backend dependencies from `backend/requirements.txt`; it may not collect in environments missing `passlib` or other declared packages.
