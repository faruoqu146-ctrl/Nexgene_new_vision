# Phase 12 - NexGene Research Engine

Build `1.9.0` / engine `0.4.0` / model `nre-0.4.0-research-core`.

The Intelligence Engine v0.1 was a correlation scan: pick pairs, compute Pearson r at lags 0-2, label what survived a threshold. Phase 12 replaces it with a
research engine whose output is a *graded, auditable claim* about each relationship - and an explicit statement of what that claim can and cannot support.
The statistical core lives in `backend/app/research/` (NumPy, no I/O, deterministic). `main.py` only gathers data, calls the engine and persists the result.

## 1. What changed and why

| v0.1 behaviour | Problem | Phase 12 |
|---|---|---|
| Pearson r with a Student-t (or effective-N) p-value | On autocorrelated daily data a naive test makes far more false positives than its nominal rate (measured, see validation report) | Weekday/trend-adjusted partial correlation; **conservative maximum of three tests**: shift-calibrated empirical null, Newey-West HAC, Bartlett effective-N |
| Candidates prefiltered at `abs(r) >= 0.30`, then Benjamini-Hochberg | BH after a data-dependent filter is not BH over the tested family; the README claim "all tested candidates" was not true | The **whole family** is tested (no effect-size prefilter); BH within a pre-specified *primary* family and an *exploratory* family |
| Same-day pairs tested in both directions | Identical statistics counted twice, inflating the family and creating mirrored hypotheses | Same-day pairs are **undirected** and appear once |
| Circular-shift test only when the series had no gaps | Real self-tracking data always has gaps, so the test rarely ran | Shift test works on the **calendar grid with NaN gaps**; offsets near *every* hypothesised lag are excluded; p-value is continuous (effective-shifts degrees of freedom) |
| Single-day predictions judged with a +/-2% tolerance | One noisy day cannot validate anything | **Locked-model forward tests** with sequential evidence ratios (section 3.10) |
| Status = threshold on r, q, n | Opaque, easy to over-read | **Evidence Readiness Levels** decided by explicit gates (section 3.9) |
| Effect reported only as r | Not interpretable | Effect in natural units with interval, per-SD effect, shrunk (winner's-curse-corrected) estimate, Bayes factor, E-value |
| No notion of data sufficiency | The engine never said what it *couldn't* detect | Minimum detectable effect and days-needed reported |
| Naive SQLite datetimes passed to `astimezone()` | Python treats a naive value as *server-local* time; correct only if the server runs in UTC | Naive datetimes are treated as UTC everywhere |
| 7-day vs 21-day mean with fixed thresholds | Arbitrary, unknown false-alarm rate | Robust baseline + CUSUM + recent-window test with measured behaviour |
| Nothing to separate association from effect | Observational scan can never show an effect | Pre-registered **randomised self-experiments** (N-of-1) |

## 2. Architecture

```text
Observation + BiomarkerSignal rows
        |  panel.build_panel   (timezone-correct daily grid, NaN gaps, no imputation)
        v
      Panel --- panel_quality ---> eligible variables, quality score, warnings
        |
        |  discovery.analyze_panel
        |     inference.screen_pair      every candidate in the family
        |     multiplicity               BH / BY / Holm within each family
        |     bayes                      empirical-Bayes shrinkage, Bayes factors
        |     inference.robustness       bootstrap, leave-week-out, winsorised, Spearman, high-pass, split-half
        |     inference.directional_*    AR-controlled forward and reverse tests (lagged pairs)
        |     inference.e_value / power  sensitivity to confounding, detectable effect, days needed
        |     gates.evaluate_gates       ERL-0..5 and status
        |     spc.analyze_drift          baseline drift per variable
        v
  ResearchResult --- narrative.build_brief ---> plain-language brief
        |            provenance.make_manifest -> hash-chained run receipt
        |
  forecast.freeze_model / score_frozen / summarize_track  ---> gates (ERL-4)
  experiment.design_experiment / analyze_experiment       ---> gates (ERL-5)
```

| Module | Responsibility |
|---|---|
| `special.py` | Student-t, F, normal, incomplete-beta (stdlib only; cross-checked against SciPy to ~1e-12) |
| `config.py` | `EngineConfig`, versions, variable taxonomy, ERL ladder |
| `panel.py` | Daily panel, quality profiling, content hash |
| `inference.py` | Residualisation, calibrated screening, HAC, shift null, robustness, directional tests, E-value, power |
| `multiplicity.py`, `bayes.py` | FDR/FWER adjustment; empirical Bayes, Bayes factors |
| `discovery.py` | Candidate family, pipeline orchestration, `ResearchResult` |
| `gates.py` | Evidence gates and tiers |
| `forecast.py` | Locked-model forward testing |
| `experiment.py` | Randomised self-experiments |
| `spc.py` | Robust baselines, CUSUM, EWMA-style recent-window test |
| `provenance.py` | Canonical JSON, code fingerprint, manifests, chain verification |
| `narrative.py` | Tier-controlled wording, next-experiment ranking |
| `evidence.py`, `meta.py` | Literature context and reviewed priors; random-effects pooling (maths only) |
| `simulate.py`, `validate.py`, `cli.py` | Synthetic generators, validation studies, CSV command line |

## 3. Methods

### 3.1 Panel and data quality
One slot per local calendar day in the user's timezone. Several entries on a day are averaged and flagged. Missing days are `NaN`: never imputed, never zero.
Naive datetimes (SQLite) are treated as UTC. Variables need >= 10 observed days, >= 3 distinct values and no straight-lining (modal share <= 85%).
Quality is a transparent 0-100 heuristic (coverage, regularity, variability, breadth, depth); it is not a validated instrument.

### 3.2 Adjustment
Every series is residualised on weekday indicators and a linear trend using its own observed days (falling back to intercept + trend when there are too few
observations). The correlation of the residuals equals the covariate-adjusted partial correlation (Frisch-Waugh-Lovell). Raw r is reported alongside.

### 3.3 Calibrated p-value
For a candidate (x, y, lag) the adjusted r uses calendar-lag pairs (x on day t with y on day t+lag; a pair exists only if both days were observed).
Three p-values are computed and the **largest** is reported:

1. **Shift-calibrated empirical null.** y is circularly shifted to every offset outside `[-buffer, max_lag + buffer]`, i.e. alignments that are not near *any* hypothesised lag.
   The root-mean-square of the null z-statistics (floored at 1.0, i.e. never more optimistic than independent-data theory) rescales the observed z; the reference is Student-t
   with degrees of freedom equal to the *effective number of independent shifts*, estimated from the null sequence's own autocorrelation.
   This preserves autocorrelation, heaping and gap patterns without assuming AR(1).
2. **Newey-West HAC** slope test (Bartlett kernel on the gappy grid). Known to be too optimistic in short, persistent series - which is why it is only one of three.
3. **Bartlett effective-N** t-test from the series' autocorrelations.

The Fisher-z interval uses the shift-calibrated standard error.

### 3.4 Families and multiplicity
Every ordered pair at lags 1..2 and every unordered same-day pair among eligible variables is tested (cap: 24 variables, best covered first).
A candidate is in the **primary** family when its exposure is a modifiable behaviour and its outcome a state per the variable taxonomy in `config.py`
(a product taxonomy, not a medical claim); everything else is **exploratory**. Benjamini-Hochberg q-values are computed within each family over all of its candidates;
Benjamini-Yekutieli and Holm are reported alongside. The family is defined from variable names, never from the data.

**Echoes.** A real relationship between persistent series appears, weaker, at neighbouring lags and in the reverse orientation. Those associations are statistically genuine (validated: they are not false discoveries), but listing each as a separate finding is misleading. For each variable pair the strongest candidate is the dominant finding; the others are labelled `echo_of` and omitted from the brief (it lists `also_seen_at`). Tiers are not changed by this labelling.

### 3.5 Bayesian layer
A two-group empirical-Bayes model on the Fisher-z scale estimates the null fraction and effect scale from the whole family and returns, per candidate, the posterior probability the
association is non-zero, its local false-discovery rate, and a shrunk effect (winner's-curse correction). A separate default-prior summary gives a Bayes factor,
probability of direction and probability of a practically meaningful effect (|r| > 0.10). Tests share variables and are therefore dependent; the mixture treats them as exchangeable.

### 3.6 Robustness
For candidates that could plausibly reach a claim (family q <= 0.25 or p <= 0.05, at most 120): Spearman-adjusted, winsorised, leave-one-day-out, leave-one-week-out,
high-pass (rolling-median-detrended), chronological split-half, and a seeded moving-block bootstrap interval.

### 3.7 Directional testing (lagged pairs)
Does x on day t-lag add information about y on day t beyond y's own previous day, weekday and trend? The AR-controlled partial correlation is located within the same far-shift empirical
null. The reverse test (y -> x) is run too. Ordering is a stronger claim than association, so a direction is "supported" only when the forward test reaches p <= 0.01 (`directional_alpha`) while the reverse test is held to the looser 0.05 (`reverse_alpha`) unless it is clearly weaker. Same-day pairs are not testable this way.

### 3.8 Sensitivity and sufficiency
The **E-value** (VanderWeele & Ding) is computed from the adjusted standardised slope using RR ~ exp(0.91 d); it says how strongly an unmeasured confounder would have to relate to both variables to explain
the association away. It is a sensitivity analysis, not a test. The engine also reports the minimum detectable |r| at 80% power for the current effective sample size and for the primary family's multiplicity,
and the number of calendar days a single pre-registered confirmatory test would need for the shrunk effect.

### 3.9 Evidence Readiness Levels

| Level | Meaning | Gates (all must pass) |
|---|---|---|
| ERL-0 | Insufficient data / no detectable signal | fewer than 14 paired days, or p > 0.05 |
| ERL-1 | Exploratory signal | nominal p <= 0.05 but any ERL-2 gate fails |
| ERL-2 | Robust association (observational, undirected) | >= 21 paired days, >= 3 active weeks, <= 65% pair missingness; family q <= 0.05; adjusted \|r\| >= 0.20; robustness suite passes; consistent with any *reviewed* prior |
| ERL-3 | Temporally ordered association | ERL-2, lag >= 1, AR-controlled forward partial \|r\| >= 0.15 with the same sign, forward p <= 0.01, and the reverse test not significant at 0.05 (or clearly weaker) |
| ERL-4 | Prospectively confirmed | ERL-2+, locked-model evidence ratio >= 20 over >= 10 informative unseen days |
| ERL-5 | Experimentally supported | pre-registered randomised self-experiment verdict `SUPPORTED` |

Status vocabulary stays compatible with v0.1 (`TESTING`, `SUPPORTED`, `WEAKENED`, `FALSIFIED`, `INCONCLUSIVE`) and adds `CONFIRMED` (ERL-4/5) and `SUPERSEDED` (made by an older engine and not re-tested).
`WEAKENED`: locked-model evidence ratio <= 0.1 over >= 10 informative days. `FALSIFIED`: a randomised experiment refuted or contradicted the relationship.
Same-day associations cap at ERL-2 because direction is not identifiable from observational data.

### 3.10 Locked-model forward testing
When a hypothesis reaches ERL-2 the engine freezes its effect (shrunk toward zero), noise level and weekday pattern, hashes them (SHA-256) and registers a 14-day forward test as a `Prediction` row.
On each later day with both variables observed, the frozen model is compared with a no-effect model that has the same weekday and local-level terms (outcome baseline: trailing 14-day mean; exposure reference: trailing 28-day mean).
The log-likelihood ratios accumulate across days and forecasts into an evidence ratio. Because each prediction precedes its outcome the running product is a valid sequential statistic: under "no effect" the chance it ever reaches 20 is at most 5% (Ville's inequality; approximate here because the noise level is estimated).
Legacy single-day predictions are retired as `INCONCLUSIVE` rather than scored under a different protocol.

### 3.11 Randomised self-experiments (N-of-1)
Blocks of two equal periods; the order of *usual* (A) and *intervention* (B) within each block is randomised from SHA-256 of (seed, block), so a schedule reproduces exactly on any machine.
The analysis plan, schedule and seed are hashed before any data exist. Effect estimates are **withheld until the schedule is complete** (no optional stopping). Analysis:
intention-to-treat mean of within-block B-A differences with an exact sign-flip randomisation test (Monte Carlo above 16 blocks), a randomisation-inversion 95% interval, a manipulation check on the logged exposure,
a secondary complier (Wald) effect, and a Bayesian posterior. Verdicts: `SUPPORTED`, `CONTRADICTED`, `REFUTED` (90% interval inside +/-0.2 outcome SD), `INCONCLUSIVE`.
Only one experiment may be active per user. Experiments cannot be blinded and say nothing about other people.

### 3.12 Baselines
Robust median/MAD baseline from all but the last 7 days, widened for serial correlation; two-sided tabular CUSUM (k = 0.5, h = 5) and a recent-window mean test; single-day extremes by modified z-score.

### 3.13 Provenance
Each run records the SHA-256 of the input panel, the config, the seed (derived from the input hash unless set), a fingerprint of the research package source, the results digest, and the previous run's hash.
`GET /api/v1/intelligence/research/manifest` returns the chain and verifies it. Re-running on identical data reproduces the results hash.

### 3.14 Population pooling (not wired)
`meta.py` implements DerSimonian-Laird random effects with Hartung-Knapp intervals and refuses to pool fewer than 10 people. Cross-user pooling needs consent, governance and de-identification that do **not** exist yet.

### 3.15 Literature and priors
Stored evidence sources that mention *both* variables are attached to a hypothesis as retrieved context (`appraised: false`) with generated search queries. This never changes a p-value or a tier.
An optional priors file (`RESEARCH_PRIORS_PATH`; see `knowledge/priors.example.json`) is honoured only for entries marked `reviewed` with citations, and only as a direction-concordance gate.

## 4. API
Unchanged paths with added fields: `POST /api/v1/intelligence/engine/run`, `GET .../engine/status`, `GET .../hypotheses`, `GET .../predictions`, `GET .../audit/{hypothesis_id}`.
Added: `GET .../research/brief`, `GET .../research/manifest`, `POST|GET .../experiments`, `GET .../experiments/{id}`, `POST .../experiments/{id}/analyze`, `POST .../experiments/{id}/abandon`.
Every route requires authentication; every POST requires CSRF; run/create/analyze are rate limited; all rows are user-scoped.

## 5. Data model
One new table, `experiments`. Existing tables are reused: `Hypothesis.effect_estimate` is now the **adjusted** r; `Hypothesis.confidence` is the posterior probability that the association is non-zero (never a probability of causation);
`Hypothesis.statistical_test_json` carries tier, gates and full analysis; `Prediction` rows are locked forward tests (`evaluation_json.preregistration`, later `.scoring`); `IntelligenceRun.summary_json` carries the brief and manifest.

## 6. Configuration
All analytical settings are fields of `EngineConfig` (windows, minimum days, lags, q thresholds, effect floor, bootstrap size, forecast horizon, evidence-ratio thresholds, drift parameters, seed). They are hashed into every manifest.
Environment: `RESEARCH_PRIORS_PATH` (optional reviewed priors file).

## 7. Limitations (read these)
- Everything is observational except ERL-5, and ERL-5 applies to one person in one period.
- Error rates were measured **only on synthetic data**. Real self-tracking data has informative missingness, reporting drift, travel, illness and measurement artefacts that the simulations do not contain.
- Linear, additive, adjusted associations only: no thresholds, interactions, mediation, or non-linear dose-response.
- Same-day measurements share context; direction is not identifiable. Lagged tests are still observational.
- Candidate tests share variables and lags of the same pair are strongly dependent; BH control under this dependence is verified empirically, not proven.
- With a single person and about 90 days the family-wide correction means only strong relationships (|r| of roughly 0.45-0.6) can reach ERL-2. The engine states this rather than hiding it.
- The weekday + linear-trend adjustment cannot remove irregular shared events.
- Self-reported 0-10 scales are ordinal and are treated as interval; Spearman is a sensitivity check only.
- E-values rest on an approximation (RR ~ exp(0.91 d)) and a single hypothetical confounder.
- The taxonomy that defines the primary family encodes product judgement, not medical knowledge.
- No part of this is a medical device, a diagnosis, or treatment guidance.

## 8. Deliberately not built yet
Cross-user pooling governance; genomic/clinical priors; wearable ingestion; informative-missingness models; multilevel models; non-linear and interaction effects; mediation; carry-over modelling in experiments; a UI for experiments (the mobile UI remains frozen).

## 9. Run and verify
```bash
python -m backend.app.research.cli demo                      # synthetic example, no database
python -m backend.app.research.cli analyze export.csv --md report.md --out report.json
python -m backend.app.research.validate --quick               # error-control and power studies (minutes)
pytest backend/tests -q                                       # full suite (needs requirements.txt installed)
```
