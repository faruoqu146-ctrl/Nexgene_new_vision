# NexGene Phase 0–1 Status (2026-10-19)

## Target repository
`faruoqu146-ctrl/Nexgene_new_vision` @ main

## Phase 0 — Ground truth
- Multiple repos surveyed; this repo selected as primary (most recent comprehensive research engine).
- Stack: FastAPI monolith + research package (`backend/app/research/`) + static mobile UI.
- Compartmented DBs (main / clinical / genomic), PubMed/Crossref live evidence path present.
- Research engine already implements calendar lags, conservative multiplicity, ERL gates, N-of-1 scaffolding.

## Phase 1 — Foundation stabilisation (done locally; partially on remote)

### Done and verified (146 research+security tests pass under DEV_MODE=true)
1. **Gates honesty** (`backend/app/research/gates.py`) — on remote
   - Machine-friendly reasons: `insufficient_data`, `no_detectable_signal`, …
   - Reviewed prior disagreement blocks above ERL-1
   - Robustness diagnostics required for ERL-2+
2. **Security test suite** (`backend/tests/test_security.py`) — on remote
   - `ensure_user` helper; 13/13 pass
3. **Auth/session robustness** (`backend/app/main.py`) — verified locally; **remote file was overwritten by PLACEHOLDER and must be restored**
   - `_as_utc` for SQLite naive datetimes
   - `COOKIE_SECURE` defaults false under DEV_MODE
   - Rate-limit no-op under DEV_MODE
   - Valid `DUMMY_PASSWORD_HASH`

### Blocker
`backend/app/main.py` on remote currently contains the string `PLACEHOLDER` from an interrupted bulk push. Local tree has the full patched file (153212 bytes). Restore is required before any deployment.

## Phase 2 — Started
- Purpose-specific consent module: `backend/app/governance/consent.py`
- Canonical observation contract: `backend/app/governance/models_contract.py`
- Tests: `test_consent.py`, `test_canonical_observation.py`

## Next
1. Restore `main.py` on remote from local verified copy.
2. Wire consent records into DB + check-in / intelligence paths.
3. Enrich Observation table with canonical fields (nullable, backward compatible).
4. Lifestyle completion gate checklist.
