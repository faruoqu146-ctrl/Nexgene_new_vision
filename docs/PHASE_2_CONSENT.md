# Phase 2 — Consent and canonical observations

## What landed

### ConsentRecord (DB)
- Table `consent_records`: user_id, purpose, data_category, granted, policy_version, granted_at, revoked_at
- Unique on (user_id, purpose, data_category)

### Purposes
- `collect`, `personal_insight`, `cross_domain`, `prediction`, `research`, `export`
- Default lifestyle grant on first check-in: `collect` + `personal_insight` only

### API
- `GET /api/v1/consent?data_category=lifestyle` — list grants
- `PUT /api/v1/consent` — grant/revoke one purpose (CSRF required)

### Observation enrichment (backward compatible)
Nullable/defaulted columns: `data_domain`, `source_type`, `unit`, `quality_flag`, `observed_at`, `period`
Check-ins set: domain=lifestyle, source_type=user-entered, quality=self_reported, period=morning|evening

### Enforcement
- Check-in requires `collect` consent for lifestyle; returns 403 if revoked

## Verify
```bash
export DEV_MODE=true SECRET_KEY=testsecretkeyfornexgene123456789012345
PYTHONPATH=. pytest backend/tests/test_consent_api.py backend/tests/test_security.py -q
```
