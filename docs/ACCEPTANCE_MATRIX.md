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
| Check-in ingestion + provenance links | PASS |
| Canonical observation fields | PASS |
| Purpose-specific consent model + API | PASS |
| Default lifestyle consent (collect + personal_insight) | PASS |
| Collect required for check-in | PASS |
| Personal_insight required for engine run | PASS |
| Personal_insight required for research brief | PASS |
| Descriptive baselines endpoint | PASS |
| Coverage / lifestyle_layer_ready gate | PASS |
| Multi-day baseline readiness (7+ days) | PASS (criterion) |
| Research secondary-use (PURPOSE_RESEARCH) enforcement | TODO |
| Cross-domain combination gate | TODO |
| UI surfaces for uncertainty / null results | TODO |
| Clinical validation of lifestyle layer | NOT CLAIMED |

## What NexGene can do now
- Collect lifestyle check-ins with provenance and consent
- Grant/revoke purpose-specific consent
- Run personal association analysis under ERL gates when consent allows
- Report descriptive personal baselines without clinical claims
- Report lifestyle_layer_ready for product gating

## What NexGene cannot yet claim
- Causal effects from observational lifestyle data alone
- Clinical or diagnostic use
- Validated predictive models for treatment decisions
- Secondary research reuse without explicit PURPOSE_RESEARCH grant
