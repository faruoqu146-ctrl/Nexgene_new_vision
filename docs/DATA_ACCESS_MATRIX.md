# NexGene Internal Data-Access Matrix (Directive 01)

Concise matrix of **who** may perform **which operation** on **which domain**, and **how enforcement is implemented**.
Last verified: 2026-10-20 against `main` test suite (207 tests including provider E2E).

Legend for enforcement:
- **Route** = checked in FastAPI handler
- **Dual** = user grant + provider grant required
- **Purpose** = purpose-scoped consent record
- **Tested** = covered by automated tests

| Actor | Subject | Domain | Operation | Purpose / auth required | Enforcement | Tested |
|-------|---------|--------|-----------|-------------------------|-------------|--------|
| User (session) | self | lifestyle | write check-in | `collect` | Route + Purpose | Yes |
| User | self | lifestyle | run research engine | `personal_insight` | Route + Purpose | Yes |
| User | self | lifestyle | research brief | `personal_insight` | Route + Purpose | Yes |
| User | self | lifestyle | secondary research status | `research` (default deny) | Route + Purpose | Yes |
| User | self | physiological | write via check-in | `collect` (lifestyle path; domain tag physiological) | Route + Purpose | Yes |
| User | self | molecular | write biomarker signals | `collect` on `molecular` | Route + Purpose | Yes |
| User | self | molecular | read own biomarkers | session | Route (user_id filter) | Yes |
| User | self | clinical | consent / revoke | session + CSRF | Route | Yes |
| User | self | clinical | read records | dual-auth | Dual + Route | Yes |
| Clinical provider | linked subject_ref | clinical | provider grant | `X-Clinical-Provider-Key` | Dual + HMAC key | Yes |
| Clinical provider | linked subject_ref | clinical | sync records | dual-auth + key | Dual + Route | Yes |
| User | self | genomic | consent / revoke | session + CSRF | Route | Yes |
| User | self | genomic | read variants/PRS | dual-auth | Dual + Route | Yes |
| Genomic provider | linked subject_ref | genomic | grant / sync | `X-Genomic-Provider-Key` | Dual + HMAC key | Yes |
| User | self | clinical+lifestyle combine | intelligence clinical_context | `cross_domain` + dual clinical | Purpose + Dual | Yes |
| Any other user | another user | any | read/write | denied | user_id scoping | Yes |
| Unauthenticated | — | any personal | read/write | denied | session cookie | Yes |
| Background learning worker | configured users | lifestyle-derived | offline cycle | deployment-controlled | Script, not public API | Partial |

## Explicit gaps (not fully closed)

1. **Service-layer centralization** — Authorization is primarily route-level, not a single data-access service. A future internal module call could bypass a route if introduced carelessly.
2. **Derived/cached results after revoke** — Engine run is blocked after `personal_insight` revoke; historical Hypothesis rows may still exist for the user (user-scoped read). Cross-user leakage of derived rows is tested; post-revoke purge policy is not fully specified.
3. **Export / secondary research release** — Status API exists; no bulk export pipeline.
4. **Provider key rotation / audit log query API** — Grants store timestamps; no dedicated audit query surface.

## Non-claims

This matrix documents **intended and tested** controls. It is not a regulatory compliance certification.
