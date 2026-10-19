# NexGene Acceptance Matrix (2026-10-19)

Legend: PASS = verified with tests | PARTIAL = implemented, limited coverage | TODO = not yet

## Phase 0 — Ground truth
| Item | Status |
|------|--------|
| Primary repo selected (Nexgene_new_vision) | PASS |
| Research engine preserved | PASS |
| Test suite executable | PASS |

## Phase 1 — Foundation
| Item | Status |
|------|--------|
| ERL gates honest reasons | PASS |
| Auth/session timezone safety | PASS |
| DEV_MODE rate-limit / cookie defaults | PASS |
| Security suite (CSRF, isolation, logout) | PASS |
| Cross-user data isolation | PASS |

## Phase 2 — Lifestyle intelligence
| Item | Status |
|------|--------|
| Check-in ingestion + provenance | PASS |
| Canonical observation fields | PASS |
| Purpose-specific consent API | PASS |
| Collect required for check-in | PASS |
| Personal_insight for engine + research brief | PASS |
| Descriptive baselines + coverage gate | PASS |
| Secondary research denied by default | PASS |
| Cross-domain required for clinical+lifestyle combine | PASS |
| Clinical validation of lifestyle layer | NOT CLAIMED |

## Phase 3 — Clinical compartment (in progress)
| Item | Status |
|------|--------|
| Separate clinical store | PASS |
| Dual authorization (user + provider) | PASS |
| User consent alone insufficient | PASS |
| Records empty without dual auth | PASS |
| Grants user-scoped | PASS |
| Provider routes closed without key | PASS |
| Full provider sync integration tests | PARTIAL (needs CLINICAL_PROVIDER_KEY) |
| Genomic dual-auth parity tests | PASS |

## What NexGene can do now
- Lifestyle collection, consent, baselines, coverage gating
- Personal association analysis under ERL with calibrated nulls
- Clinical dual-auth compartment (separate DB)
- Explicit denial of secondary research and cross-domain combine without purpose grants

## What NexGene cannot yet claim
- Causal inference from observational data alone
- Clinical/diagnostic use or validated treatment predictions
- Secondary research data release pipelines
- Full genomic provider integration test coverage

## Operational repairs (Directive 01)
| Item | Status |
|------|--------|
| Demo seed blocked without DEV_MODE/ALLOW_DEMO_SEED | PASS |
| Dockerfile does not unconditionally seed | PASS |
| Clinical DB URL on shared volume in Compose | PASS |
| Genomic dual-auth parity tests | PASS |
| Full pytest suite continuous CI | TODO |
| Provider-key E2E dual-auth sync tests | PARTIAL |
