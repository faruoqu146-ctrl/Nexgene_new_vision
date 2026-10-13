# Phase 12 - Validation Report

Engine `0.4.0` (`nre-0.4.0-research-core`), build `1.9.0`. Environment: Python 3.12.3, NumPy 2.4.4, SciPy 1.17.1 (cross-checks only), no network.

## 1. Summary

The statistical machinery behaves as designed **on synthetic data**: false-positive rates sit near their nominal levels where a naive correlation test is badly miscalibrated, false-discovery
control is approximately nominal in the pipeline as a whole, forward testing and randomised experiments have the error control their theory predicts, and power is quantified. **Nothing here has been validated on real
people.** Real self-tracking data breaks the simulator's assumptions in ways that cannot be enumerated (informative missingness, reporting drift, illness, travel, non-linear effects).
The web layer (`main.py`) was verified by static contract tests and an end-to-end rehearsal through stand-ins for FastAPI/SQLAlchemy/Pydantic; the real web stack was **not** available in the verification environment.

## 2. What was and was not verified

| Area | Evidence | Status |
|---|---|---|
| Research package (`backend/app/research/`) | 144 tests, namespace pytest-compatible runner: 144 passed | Verified |
| Special functions, BH/BY/Holm | SciPy cross-check (section 3), reference-loop comparison | Verified |
| Statistical error control | Simulation studies (sections 4-7) | Verified on synthetic data only |
| `main.py` integration | Static contract tests (AST: CSRF on every POST, auth on every route, user scoping, ORM attribute names) + end-to-end rehearsal of engine run, persistence, forward-test freeze and scoring, experiment design/interim/final analysis, hypothesis promotion to ERL-5, empty user, cross-user isolation | Verified through stand-ins; **real FastAPI/SQLAlchemy not run** |
| `backend/tests/test_research_api.py` | Written (TestClient: auth, CSRF, run, brief, experiment lifecycle, isolation) | **Not executed here** - run `pytest backend/tests -q` with `requirements.txt` installed |
| `test_security.py`, `test_clinical_compartment.py` | Unchanged from the supplied build | **Not executed here** |
| Real data | None | Not validated |

The supplied `test_intelligence_engine_v01.py` asserted a `1.7.0-intelligence-v0.1` build string that did not match the supplied code (`BUILD_VERSION = APP_VERSION`), so it could not have passed; the legacy math/guard tests imported helpers that no longer exist.
They were replaced by tests of the same intent against the new package (calendar lags never bridge gaps, no zero imputation, conservative combination never more optimistic than any component, shared weekly cycle/trend not mistaken for a relationship).

## 3. Numerical correctness

| Function | Max error vs SciPy 1.17 (20,000 random points) |
|---|---|
| Student-t two-sided p (relative) | 2.5e-12 |
| Student-t quantile (relative, incl. extreme tails and df 1-5000) | 4.2e-13 |
| Regularised incomplete beta (absolute) | 4.2e-14 |
| F survival (absolute) | 2.5e-14 |
| Normal quantile (absolute) | 1.3e-15 |

Benjamini-Hochberg, Benjamini-Yekutieli and Holm adjustments matched straightforward reference loops on 500/500 random families. The E-value, minimum detectable r and days-needed functions are checked against closed forms in the test-suite.

## 4. Calibration of the p-value (independent pairs, no relationship)

Pairs of *independent* autocorrelated series with a shared weekly cycle and trend (so the raw correlation is spuriously inflated). Rejection rate at nominal alpha = 0.05; 1,800 tests per row
(binomial standard error about 0.5%).

| Setting | Tests | Naive Pearson | HAC | Bartlett effective-N | Shift-calibrated | **Reported (max of three)** | Reported at alpha 0.001 |
|---|---|---|---|---|---|---|---|
| T=60, AR=0.0, 10% missing | 1800 | 11.2% | 10.5% | 6.9% | 5.6% | 5.2% | 0.17% |
| T=60, AR=0.5, 10% missing | 1800 | 18.1% | 14.3% | 7.2% | 5.5% | 4.6% | 0.00% |
| T=60, AR=0.8, 10% missing | 1800 | 30.1% | 23.4% | 8.6% | 6.2% | 4.9% | 0.00% |
| T=90, AR=0.5, 20% missing, 0-10 integer scale | 1800 | 16.9% | 13.3% | 6.6% | 6.3% | 5.3% | 0.06% |
| T=45, AR=0.6, 15% missing | 1800 | 15.6% | 19.2% | 7.8% | 5.5% | 4.6% | 0.00% |

A naive correlation test produces 11-30% false positives at a nominal 5%. HAC alone is also too optimistic in short, persistent series (up to 23%), which is why it is only one of three tests.
The reported p-value is the largest of the three and stays at 4.6-5.3%.

## 5. Error control of the whole pipeline

### 5.1 Complete null (no real relationship anywhere)
600 panels x 8 variables (84,000 candidates). Any ERL-2 claim is a false discovery.

| Setting | Panels | Panels with a false ERL-2 claim (95% CI) | Per-candidate false positives at p <= 0.05 |
|---|---|---|---|
| T=60, AR=0.3, 10% missing | 150 | 4.7% (2.3-9.3%) | 4.50% |
| T=90, AR=0.5, 10% missing | 150 | 4.0% (1.8-8.5%) | 4.11% |
| T=90, AR=0.8, 15% missing | 150 | 2.0% (0.7-5.7%) | 4.92% |
| T=120, AR=0.5, 20% missing, 0-10 integer scale | 150 | 6.0% (3.2-11.0%) | 4.30% |
| **All** | **600** | **4.2% (2.8-6.1%)** | **4.46%** |

Under a complete null, FDR control means roughly a 5% chance of any claim per panel. The 95% interval of the effect estimate excluded zero for 5.3% of candidates (target 5%).
18 of 600 panels (3.0%) also contained a false ERL-3 claim; most false ERL-2 claims at lags >= 1 pass the directional gate because the directional test is evaluated on
candidates already selected for apparent association.

### 5.2 Four real effects among 24 unconnected variable pairs
Planted: activity -> mood (lag 1), stress -> focus (same day), caffeine -> sleep quality (lag 1), alcohol -> energy (lag 1); strengths 0.4-1.4 (standardised coefficient), 8 variables, 10% missing, AR(1) = 0.5.
Every ERL-2 claim is classified against the known generating graph: **planted** (the exact relationship), **echo** (same pair, other lag or orientation - statistically genuine because persistent series
carry a real relationship into neighbouring lags, not a false discovery), **spurious** (a pair with no connection at all, i.e. a true null).

| T (days) | Panels | ERL-2 claims | Planted | Echo of a planted pair | **Spurious** (pooled; 95% CI) | Mean per-panel false-discovery proportion | ERL-3 claims with the correct planted direction |
|---|---|---|---|---|---|---|---|
| 60 | 120 | 297 | 262 (88%) | 25 (8%) | 10 (3.4%; 1.8-6.1%) | 1.5% | 203/207 (98%) |
| 90 | 120 | 466 | 331 (71%) | 121 (26%) | 14 (3.0%; 1.8-5.0%) | 1.9% | 258/263 (98%) |
| 120 | 120 | 657 | 380 (58%) | 231 (35%) | 46 (7.0%; 5.3-9.2%) | 4.6% | 287/304 (94%) |

The quantity Benjamini-Hochberg controls is the *expected* false-discovery proportion; it was 1.5%, 1.9% and 4.6%
against a 5% target. The pooled spurious fraction at T = 120 (7.0%, interval 5.3-9.2%) is slightly above 5% because panels with many claims weigh more in a pooled ratio; a
fresh-seed check of 60 panels at T = 120 gave 4.7% pooled and 3.2% mean. Treat the engine's FDR control as approximately nominal, not guaranteed.
Echo associations are labelled (`echo_of`) and collapsed to one finding per variable pair in the brief; their tiers are not changed.

## 6. Power (ERL-2 detection of a planted relationship)

Each row: 120 planted-effect trials. Strength is the standardised planted coefficient (roughly r = strength / sqrt(1 + strength^2) before attenuation by noise and adjustment).
ERL-3 is capped by design at the three lagged effects (same-day effects cannot be ordered), so about 75% is the ceiling.

| T (days) | Planted strength | Power ERL >= 2 (95% CI) | Power ERL >= 3 | Sign accuracy | Trials |
|---|---|---|---|---|---|
| 60 | 0.4 | 4% (2-9%) | 3% | 98% | 120 |
| 60 | 0.7 | 38% (30-47%) | 32% | 100% | 120 |
| 60 | 1.0 | 80% (72-86%) | 60% | 100% | 120 |
| 60 | 1.4 | 96% (91-98%) | 73% | 100% | 120 |
| 90 | 0.4 | 12% (7-19%) | 9% | 100% | 120 |
| 90 | 0.7 | 68% (60-76%) | 57% | 100% | 120 |
| 90 | 1.0 | 96% (91-98%) | 73% | 100% | 120 |
| 90 | 1.4 | 100% (97-100%) | 75% | 100% | 120 |
| 120 | 0.4 | 27% (20-35%) | 21% | 100% | 120 |
| 120 | 0.7 | 90% (83-94%) | 68% | 100% | 120 |
| 120 | 1.0 | 100% (97-100%) | 75% | 100% | 120 |
| 120 | 1.4 | 100% (97-100%) | 75% | 100% | 120 |

Practical reading: with one person, 8 logged variables and about 90 days, only fairly strong relationships (standardised strength 0.7 or more) are reliably recovered after correcting for the whole family; weak ones need
roughly 4 months or a targeted self-experiment. The engine reports this threshold as `sufficiency` rather than hiding it.

## 7. Other components

### 7.1 Randomised self-experiment test
Exact sign-flip test when outcomes are autocorrelated and unaffected by assignment (3,000 replicates per row, binomial SE 0.4%). Theory: size <= 5% regardless of autocorrelation.

| Blocks | Period length (days) | Outcome AR(1) | Replicates | Rejection rate at 0.05 |
|---|---|---|---|---|
| 14 | 1 | 0.0 | 3000 | 4.77% |
| 14 | 1 | 0.5 | 3000 | 6.13% |
| 14 | 1 | 0.8 | 3000 | 5.37% |
| 10 | 2 | 0.5 | 3000 | 5.23% |
| 8 | 3 | 0.5 | 3000 | 4.93% |
| 20 | 1 | 0.5 | 3000 | 4.40% |

One reading (6.13%, blocks = 14, AR = 0.5) is 2.9 standard errors above 5%. It did not replicate: three further 8,000-replicate runs of that configuration gave 5.34%, 4.83% and 5.24%, and an i.i.d. reference gave 4.94%.

### 7.2 Locked-model forward test
Frozen on 80 days, scored on 50 unseen days. The frozen candidate is the *top-ranked candidate chosen by the data*, the hardest case for a forward test. 120 replicates per row.

| Truth | Selected the true pair | Median evidence ratio | P(ratio >= 20) | P(ratio >= 3) | P(ratio <= 0.1) | Median skill vs no-effect model |
|---|---|---|---|---|---|---|
| No real effect | 2% | 1.00 | 0.0% | 3.3% | 4.2% | -0.000 |
| Planted effect (0.8) | 90% | 86.5 | 65.0% | 76.7% | 2.5% | +0.203 |

Under no effect the evidence ratio never reached the confirmation threshold of 20 (Ville bound: at most 5%).

### 7.3 Drift detectors
Stable and shifted AR(1) series (rho = 0.5, 15% missing days, 90 days); 500 series per row. The shift occurs in the last N days.

| Level shift (outcome SD) | Last N days | CUSUM alarm rate | Recent-window alarm rate |
|---|---|---|---|
| none (stable) | - | 1.8% | 2.2% |
| 1.5 | 7 | 23.8% | 40.6% |
| 1.5 | 14 | 32.8% | 26.8% |
| 2.5 | 7 | 63.8% | 84.6% |
| 1.0 | 21 | 10.8% | 7.4% |

False alarms are about 2%. Sensitivity to short, modest shifts is limited by serial correlation in the data (a level shift is hard to tell from a noise excursion in a short window); it is a property of the problem, not only of the detector.

### 7.4 Run time (one full analysis, 90 days, 10% missing, single CPU core)
| Variables | Candidates | Time |
|---|---|---|
| 6 | 75 | 0.16 s |
| 8 | 140 | 0.21 s |
| 12 | 330 | 0.49 s |
| 24 | 1380 | 1.41 s |

## 8. Problems found during validation and what changed

| Finding | Action |
|---|---|
| A fixed degrees-of-freedom rule for the shift null gave up to 9.2% false positives at AR = 0.8 in the first calibration run | Replaced by effective-shifts degrees of freedom estimated from the null sequence's own autocorrelation; the shift test alone then measured 5.5-6.3% and the reported maximum of three tests 4.6-5.3% (section 4) |
| Effect-size prefilter before Benjamini-Hochberg (v0.1) | Removed; whole family tested |
| Lag-0 pairs tested in both directions (v0.1) | Same-day pairs are undirected |
| Naive SQLite datetimes were passed to `astimezone()` (server-local assumption) | Treated as UTC everywhere |
| A planted effect plus persistence produced many "false" claims under a naive truth definition | Claims classified planted / echo / spurious; echoes labelled and collapsed in the brief |
| Spurious ERL-3 claims cleared a 5% directional gate | Forward test must reach p <= 0.01 and the reverse test is held to 0.05 (ERL-3 wrong-direction claims 1.9-5.6%) |
| Single pure-noise panel produced a false ERL-2 claim in a unit test | Replaced the single-seed assertion with a rate test grounded in the 600-panel measurement |
| Randomisation-test size reading of 6.13% | Investigated; did not replicate (section 7.1) |
| Profiling showed the t quantile dominated run time | Newton-polished quantile with bisection fallback (accuracy 4e-13); one 8-variable analysis 0.59 s -> 0.37 s on the same panel |

## 9. Limits of this validation

- One simulator: linear AR(1) noise, a sinusoidal weekly cycle, linear trend, missing-completely-at-random days, optional rounding to a 0-10 scale. No informative missingness, regime changes, measurement error, non-linear or interaction effects.
- Only 8-24 variables, T between 45 and 120 days, planted strengths 0.4-1.4, four planted effects per panel.
- Interval widths: pooled estimates carry binomial uncertainty (see the confidence intervals); small differences between settings are not meaningful.
- Reproducibility is exact only for the same NumPy random-number-generator stream; results were produced with NumPy 2.4.4.
- No clinical validation, no external dataset, no independent replication.

## 10. Reproduce

```bash
python scripts/validation_study.py run --out validation_runs      # resumable; add --budget 150 to cap one invocation; repeat until remaining 0
python scripts/validation_study.py report --out validation_runs   # sections 4-6 as JSON
python -m backend.app.research.validate --extras --out extras.json # sections 7.1-7.4
pytest backend/tests -q                                            # full suite (needs requirements.txt)
```
