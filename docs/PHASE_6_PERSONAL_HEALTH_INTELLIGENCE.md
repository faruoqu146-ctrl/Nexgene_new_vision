# NexGene Phase 6: Personal Health Intelligence

## Purpose

Phase 6 moves NexGene from simple relationship reporting toward structured, evidence-aware longitudinal inference.

The engine does not diagnose. It separates observed changes from exploratory inferences and keeps clinical escalation as a distinct safety boundary.

## Pipeline

```text
Lifestyle + physiological + molecular signals
                    |
                    v
             Data quality layer
                    |
                    v
          Personal baseline engine
                    |
                    v
       Multi-factor longitudinal analysis
                    |
                    v
           Evidence retrieval layer
                    |
                    v
          Structured intelligence brief
                    |
                    v
        Optional AI conversational layer
```

## Personal baseline

Recent 7-day averages are compared with the preceding 21-day window when enough observations exist. The comparison is explicitly personal and is not a population-health judgment.

## Multi-factor analysis

Daily aggregates can be paired across signals such as:

- sleep and focus
- sleep and energy
- stress and focus
- activity and sleep
- caffeine and sleep

The current engine requires at least seven paired days and reports Pearson correlation only as an exploratory association. It never labels the relationship causal.

## Data quality

The intelligence layer exposes coverage, observed days, observation count, observation kinds, biomarker count, biomarker quality, and known limitations. Sparse or incomplete data is therefore visible to downstream reasoning.

## Evidence

Detected topics are passed to the local evidence registry. Evidence records retain provenance fields including title, publisher, citation, URL, year, evidence grade and topic tags.

The current registry is a development foundation, not a claim of a comprehensive medical literature corpus.

## Clinical boundary

Persistent molecular deviations can produce a conservative next-step suggestion to discuss the result with a qualified healthcare professional. v1.3 does not perform clinical triage, diagnosis, treatment selection, or emergency decision-making.

The future clinical escalation system requires separately validated criteria, clinical governance, provenance and a dedicated safety review before activation.

## AI boundary

AI receives a bounded structured packet rather than unrestricted raw health history. The deterministic analysis remains the source of facts. AI is an interpretation and communication layer and must preserve uncertainty, provenance and non-diagnostic language.
