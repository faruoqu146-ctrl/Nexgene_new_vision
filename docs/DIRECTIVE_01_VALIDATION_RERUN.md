# Directive 01 — Validation study re-run (2026-10-20)

Environment: Python 3.12, repository tip at re-run time, synthetic data only.

Command sequence:

```bash
python scripts/validation_study.py run --out validation_runs --budget 100   # repeated until remaining 0
python scripts/validation_study.py report --out validation_runs
```

Jobs completed: **57 / 57**.

## Null panels (pure noise)

| Metric | Value |
|--------|-------|
| Panels | 600 |
| False ERL-2 claim rate | **4.17%** |
| 95% CI | [2.84%, 6.08%] |
| Type-I per candidate (nominal 0.05) | 0.0446 |
| CI excludes zero rate | 0.053 |

Interpretation: under these synthetic null settings, panel-level false ERL-2 claims remain near the design target (~5%). This is **synthetic calibration evidence**, not clinical validity.

## Mixed panels (planted signals)

| T | Panels | Spurious fraction | Spurious fraction 95% CI |
|---|--------|-------------------|-------------------------|
| 60 | 120 | 3.37% | [1.84%, 6.09%] |
| 90 | 120 | 3.00% | [1.80%, 4.98%] |
| 120 | 120 | 7.00% | [5.29%, 9.21%] |

Spurious fraction rises with longer panels under the tested dependence/missingness settings. Claims remain synthetic.

## Pairwise calibration

Five settings completed. Combined reported rates at nominal levels were closer to target than naive Pearson under autocorrelation (first setting example: combined_reported ≈ 0.052 at nominal 0.05 vs naive Pearson ≈ 0.112).

## Explicit non-claims

- Does not establish performance on real human health data.
- Does not establish clinical validity or utility.
- Does not replace prospective locked evaluation for predictive use.
