# Phase 11 Validation Report

Build version: 1.8.1
Intelligence model: iei-0.3-permutation-missingness

## Summary

Phase 11 adds dependence-aware sensitivity analysis and missingness diagnostics to the Intelligence Engine. Validation confirms the circular-shift permutation is correctly gated to regular daily pairs and that the combined p-value is the more conservative of the two tests when both are available.

## Tests

- Statistical guard tests for circular-shift and missingness diagnostics.
- Contract tests for API response shape including new diagnostic fields.

## Limitations recorded

- Circular-shift is a sensitivity analysis, not a full time-series model.
- Missingness is descriptive only; no MNAR correction is applied.
