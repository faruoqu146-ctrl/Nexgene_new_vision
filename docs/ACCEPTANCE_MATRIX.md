# NexGene Acceptance Matrix (2026-10-20)

Legend: PASS = verified with tests | PARTIAL = implemented, limited coverage | TODO = not yet

## Suite status (Directive 01)
| Item | Status |
|------|--------|
| `pytest backend/tests -q` | **206 passed** (verified 2026-10-20) |
| Demo seed production refuse | PASS |
| Dockerfile gated seed | PASS |
| Clinical DB on volume | PASS |
| Consent revoke blocks collect / personal_insight | PASS |
| Cross-user timeline isolation | PASS |
| Clinical + genomic dual-auth | PASS |
| Provider-key E2E dual-auth sync | PASS |
| Continuous CI workflow | PASS (added; confirm on GH Actions) |
| validation_study.py full 57/57 re-run | PASS (synthetic) |
| validation_study in CI (bounded budget) | PARTIAL |

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

## Phase 3 — Compartments
| Item | Status |
|------|--------|
| Separate clinical store | PASS |
| Dual authorization (user + provider) | PASS |
| Genomic dual-auth parity tests | PASS |
| Provider routes closed without key | PASS |
| Full provider sync integration tests | PASS |

## What NexGene can do now
- Lifestyle collection, consent, baselines, coverage gating
- Personal association analysis under ERL with calibrated nulls
- Clinical/genomic dual-auth compartments with provider-key E2E sync path
- Explicit denial of secondary research and cross-domain combine without purpose grants

## What NexGene cannot yet claim
- Causal inference from observational data alone
- Clinical/diagnostic use or validated treatment predictions
- Secondary research data release pipelines
- Production deployment readiness (INTERNAL TEST ONLY)
