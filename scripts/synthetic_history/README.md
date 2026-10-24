# Synthetic Historical Check-ins

Versioned **synthetic** 30-day lifestyle dataset, guarded importer, cleanup, and ground-truth evaluation for NexGene New Vision.

**Non-negotiable:** these records are synthetic. They must never be presented as real participant data, clinical evidence, or proof of predictive validity.

## Files

| File | Role |
|------|------|
| `generate.py` | Deterministic dataset + ground-truth generator |
| `dataset_v1.json` | Generated observations (`synthetic=true`) — run `generate.py` if missing |
| `ground_truth_v1.json` | Pre-registered patterns & negative controls |
| `import_history.py` | Dry-run / apply importer (idempotent) |
| `cleanup.py` | Scoped delete for synthetic sources only |
| `evaluate_ground_truth.py` | Offline scoring vs ground truth |

## Safety gates

Import and cleanup refuse to run unless:

```bash
export DEV_MODE=true
# or
export ALLOW_SYNTHETIC_IMPORT=true
```

Default account: `synthetic.student@nexgene.test` / `SyntheticStudent1!`  
Override with `SYNTHETIC_IMPORT_EMAIL` / `SYNTHETIC_IMPORT_PASSWORD`.

## Quick start (local or Render shell)

```bash
cd /app   # or repo root

# 1) Generate dataset
python scripts/synthetic_history/generate.py

# 2) Dry-run
DEV_MODE=true DATABASE_URL="$DATABASE_URL" \
  python scripts/synthetic_history/import_history.py --dry-run

# 3) Small pilot (3 days)
DEV_MODE=true DATABASE_URL="$DATABASE_URL" \
  python scripts/synthetic_history/import_history.py --apply --limit-days 3

# 4) Full 30-day import
DEV_MODE=true DATABASE_URL="$DATABASE_URL" \
  python scripts/synthetic_history/import_history.py --apply

# 5) Evaluate ground truth
python scripts/synthetic_history/evaluate_ground_truth.py

# 6) Cleanup (scoped)
DEV_MODE=true DATABASE_URL="$DATABASE_URL" \
  python scripts/synthetic_history/cleanup.py --dry-run
DEV_MODE=true DATABASE_URL="$DATABASE_URL" \
  python scripts/synthetic_history/cleanup.py --apply --confirm SYNTHETIC
```

## Provenance

Source label: `SYNTHETIC {dataset_id}@{dataset_version}`  
Metadata: `synthetic=true`, dataset id/version/hash, seed, import_batch_id.

- **Event time** → `observed_at`
- **Ingestion time** → `recorded_at`

## Sign-in

- Email: `synthetic.student@nexgene.test`
- Password: `SyntheticStudent1!`
