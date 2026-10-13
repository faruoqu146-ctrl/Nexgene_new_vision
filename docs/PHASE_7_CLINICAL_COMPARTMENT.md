# Phase 7: Clinical Compartment Foundation

## Purpose

NexGene v1.5.0 introduces a separate clinical data store and a dual-authorization access model. This is a development foundation, not a hospital integration or production clinical platform.

## Compartment model

```text
Consumer application DB                 Clinical DB
------------------------                ----------------------
User identity                           Clinical records
Profile                                 Labs / diagnoses / notes
User clinical consent                   Imaging / pathology
Provider authorization                  Procedures / admissions
Opaque subject reference  ------------> subject_ref only
```

The clinical database does not use the NexGene user email or ordinary consumer session token as its record key. The bridge is an opaque `subject_ref`.

## Dual authorization

A clinical record is readable or writable only when both are present:

1. the user has explicitly authorized the provider and scope; and
2. the clinical provider has separately authorized the same opaque subject reference.

Either side can revoke. Revocation immediately removes application access to the clinical compartment.

## Development provider boundary

The prototype uses `CLINICAL_PROVIDER_KEY` and `CLINICAL_PROVIDER_ID` to simulate a trusted clinical connector. Production must replace this with a hospital-grade identity boundary such as mTLS/OAuth2/private connectivity and per-organization credentials.

## Intelligence boundary

The normal intelligence brief may receive only a small authorized clinical context: record count, record types and source systems. It does not automatically expose full clinical payloads to the consumer UI or AI. A future clinical reasoning layer must define which structured clinical facts are safe and useful to promote into inference.

## Out of scope

- FHIR implementation
- hospital onboarding
- production key management
- clinical decision support
- diagnosis or treatment recommendations
- emergency triage
- production audit/compliance certification

Those require separate clinical, security and governance reviews.
