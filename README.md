# NexGene Research Engine v0.4 - Phase 12 Build (v1.9.0)

## Phase 12: the research core

The Intelligence Engine's correlation scan has been replaced by a calibrated, auditable research engine (`backend/app/research/`). It is pure Python + NumPy, deterministic, has no I/O, and can be run on a CSV without the web stack (`python -m backend.app.research.cli demo`).

What the engine does that v0.1 could not:

- **Calibrated inference** - weekday/trend-adjusted partial correlation; an empirical circadian prior; multiplicity control (BH/BY/Holm); Bayes factors and empirical-Bayes shrinkage.
- **Discovery** - systematic scan of the effect family with gates, ranking, and provenance.
- **Forecast** - short-horizon panel forecasts with uncertainty.
- **Narrative** - human-readable research narrative from the quantitative results.
- **Validation** - contract tests, synthetic studies, and Phase 12 validation report.

See `docs/PHASE_12_RESEARCH_ENGINE.md` and `docs/PHASE_12_VALIDATION_REPORT.md` for the full design and validation.

## Quick start

```bash
# Local (no Docker)
pip install -r backend/requirements.txt
python -m backend.app.research.cli demo

# Docker
docker compose up --build
```

API docs at http://localhost:8000/docs once the server is running.

## Project layout

- `backend/app/main.py` - FastAPI app
- `backend/app/research/` - research engine (pure compute)
- `backend/tests/` - unit and contract tests
- `mobile/` - simple mobile web UI
- `docs/` - phase design and validation reports
- `knowledge/` - evidence schemas and example priors
- `scripts/` - learning cycle and validation study helpers
