# NexGene v1.5.0: Genomic + Live Evidence Intelligence Foundation

## Purpose

This phase adds a separate genomic compartment and the first live information retrieval adapters. It also establishes a recurring, versioned deterministic learning cycle.

## Genomic compartment

- Separate `GENOMIC_DATABASE_URL` store.
- Opaque `subject_ref` only in the consumer bridge.
- User consent and independent provider authorization are both required.
- Variants and polygenic scores are stored with provenance and model/source metadata.
- Revocation removes consumer access without deleting the underlying provider record.
- This is a development connector, not a hospital-grade genomic interoperability implementation.

## Live evidence

The evidence retrieval surface can query PubMed through NCBI E-utilities and scholarly metadata through Crossref. The live results are returned with source identity, identifiers and links. Production should add caching, provenance snapshots, rate controls, source validation and a dedicated retrieval/ranking layer.

NCBI E-utilities provides programmatic access to PubMed and other Entrez databases. NCBI asks callers to identify their tool/email and provides higher supported rates with an API key. Crossref's REST API provides searchable scholarly metadata and recommends a polite `mailto`/User-Agent approach. These integrations are therefore deliberately rate-limited and identifiable in code.

## Live environmental context

With user-configured city/country and live-context permission, the application can retrieve current weather/environmental context. The response is treated as contextual evidence, not as a medical measurement.

## Recurring learning

`scripts/learning_cycle.py` recalculates deterministic personal baselines over a bounded 90-day window and stores a versioned `LearningRun`. This is intentionally not a conversational AI loop. Future ML models can replace or augment this layer while retaining model versioning, input windows and provenance.

## Safety boundary

Live retrieval and genomic data do not automatically become medical conclusions. Evidence must be source-attributed, time-aware and uncertainty-aware. Clinical escalation remains a separate safety layer.
