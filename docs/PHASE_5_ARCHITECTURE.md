# Phase 5 Architecture: Molecular Signals + Evidence Intelligence

## Data flow

Lifestyle + physiological + future clinical/genetic data
→ longitudinal normalization
→ personal baseline
→ molecular/biomarker signals
→ evidence retrieval
→ structured inference
→ optional AI explanation
→ human-facing recommendation / escalation state

## Molecular signal contract

A sensor may report a meaningful deviation without providing a concentration. NexGene stores that as a deviation signal with direction, significance, confidence, quality, provenance, device identity, and calibration version.

Quantitative laboratory values use the same domain but retain numeric value and unit. NexGene must never convert a deviation-class signal into a fabricated concentration.

## Evidence contract

Evidence is a separate, provenance-preserving domain. A future large corpus should be ingested and versioned independently from user data. Retrieval should be based on the user's structured evidence packet, not unrestricted model browsing over raw health records.

## Inference contract

Every important output should distinguish:

1. observed: directly measured or recorded
2. inferred: supported by longitudinal analysis
3. evidence-backed context: supported by retrieved sources
4. next step: conservative action or monitoring suggestion
5. clinical escalation: a separate validated decision layer

Clinical escalation is deliberately `not_assessed_in_v1_2`.

## AI boundary

AI receives a bounded structured packet. It does not write observations, alter evidence records, or create clinical facts. It may explain evidence and uncertainty. A future clinical-safety layer must govern doctor-visit recommendations and urgent escalation.
