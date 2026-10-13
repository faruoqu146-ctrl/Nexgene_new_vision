# Phase 9: Living Health Baseline + Evidence Fabric

## Product question
Can NexGene start with what a person has today and progressively build a useful longitudinal health profile when existing health information is incomplete or fragmented?

## Starting-state principle
A complete digital medical record is not required.

NexGene can start with:
- self-reported health history
- lifestyle information
- simple check-ins
- any reliable information the person already has

The profile can progressively incorporate:
1. self-reported information
2. documents and paper records
3. laboratory data
4. clinical records
5. wearables / physiology
6. genomic data
7. molecular / biomarker data

## v1.6 implementation
### Provenance
`SourceRecord` represents a user-owned origin such as self-report, document, lab, clinical, wearable, genomic, or molecular data.

`ObservationSourceLink` explicitly links an observation to its origin.

Check-ins automatically create/use a `self_reported / NexGene check-ins` source and link observations to it.

### Documents
`SourceDocument` is a metadata-only manifest. It records title, type, issuer, date, checksum, and notes without storing the raw document.

This deliberately avoids turning pilot validation into a file-storage project.

### Living baseline
`GET /api/v1/baseline/living` returns:
- longitudinal stage: starting, forming, useful, established
- active days and observation count
- observation kinds
- source-layer counts
- documents and biomarker counts
- coverage across lifestyle, physiological, molecular, clinical, genetic, and document layers
- next missing layers

The stage is a product/data-readiness signal, not a clinical judgment.

### Evidence fabric
Live PubMed/Crossref retrieval now persists metadata snapshots with:
- source
- external identifier
- title
- publication metadata
- URL
- query used
- retrieval time
- content hash

This provides a foundation for reproducible evidence retrieval and later source ranking, retraction/status checks, and citation-aware intelligence.

## Deliberate non-goals
- no genomics-first pilot
- no requirement for an existing EMR
- no raw document storage in this phase
- no OCR claims
- no diagnosis or treatment engine
- no claim that a sparse baseline is clinically complete

## Next likely layer
The next intelligence step should use the source/provenance graph and evidence snapshots to produce evidence-grounded, uncertainty-aware longitudinal inferences. Those inferences should distinguish observed facts, model-derived patterns, and hypotheses.
