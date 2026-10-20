# Phase 5 scientific audit notes (Directive 01, targeted)

Date: 2026-10-20. Scope: code review + existing validate suite + 57/57 synthetic re-run.
Not a full methodological redesign.

## Confirmed strengths

1. **Missing data** — Panel stores unobserved points as `NaN` (`panel.py`); CLI documents blank ≠ zero. Pair analyses use pairwise observed masks, not zero-imputation in the core path reviewed.
2. **ERL ladder** — Documented in `config.py` ERL 0–5; `gates.py` requires data sufficiency, FDR/significance, effect floor, robustness, and treats missing robustness as not cleared. Prospective and experimental tiers require track/experiment evidence.
3. **Multiple testing** — Discovery path uses Benjamini–Hochberg family control (wired in engine; contract tests assert presence).
4. **Forward / temporal** — Lagged pairs and directional tests; same-day pairs cannot claim temporal order (gate reason explicit).
5. **Synthetic calibration** — 2026-10-20 re-run: null false ERL-2 rate ~4.17% (600 panels); mixed spurious fractions ~3–7% by T.

## Risks / limitations (do not overclaim)

| Risk | Severity | Notes |
|------|----------|-------|
| Longer panels (T=120) higher mixed spurious fraction (~7%) | Medium | Monitor; not fixed this pass |
| Autocorrelation residual type-I | Medium | Pairwise calibration prefers combined/HAC over naive Pearson; dependence remains a design constraint |
| Informative missingness | Medium | Simulated missingness is largely random in validate; real dropout mechanisms not modeled end-to-end |
| Hypothesis selection bias | Medium | Engine explores a family then gates; pre-registration is for experiments, not all exploratory pairs |
| ERL-4/5 rarity in product path | Low | Correct scientifically; product must not imply experimental support without N-of-1 completion |
| Route-level auth vs service layer | Medium | See DATA_ACCESS_MATRIX gaps |

## Changes made in this audit pass

- Documented findings (this file + DATA_ACCESS_MATRIX).
- Added regression test: panel construction does not coerce missing numeric observations to zero.

## Non-claims

Audit does not establish clinical validity, utility, or real-world predictive performance.
