NexGene

Consent-first personal health intelligence and research infrastructure.

NexGene is an early-stage platform for collecting longitudinal health observations, analysing personal patterns, and recording how strongly the available evidence supports each finding. Its long-term goal is to connect lifestyle, physiology, biomarkers, clinical records, genomic data, and external scientific evidence while preserving privacy, provenance, and uncertainty.

«Current status: Internal development and research prototype. NexGene is not a validated medical device, diagnostic system, or production-ready clinical platform. Research-engine validation is primarily synthetic; clinical validity on real people has not been established.»

What exists today

- Lifestyle tracking: Check-ins and longitudinal observations with personal baselines and data-coverage checks.
- Personal research engine: Analyses relationships in time-series data, accounts for autocorrelation and missing days, adjusts for multiple comparisons, and grades claims using Evidence Readiness Levels (ERL).
- Research transparency: Reports uncertainty, robustness checks, evidence sufficiency, and reproducibility metadata.
- Consent and data boundaries: Purpose-specific consent, user-scoped data access, and separate clinical and genomic data compartments with user and provider authorization.
- Research context: Early integrations for scholarly metadata and environmental context. These are context sources, not medical measurements.
- Development interface: A lightweight mobile web interface backed by FastAPI.

How it works

User observations
      ↓
Validated, timezone-aware daily data
      ↓
Data-quality and coverage checks
      ↓
Research engine: inference, robustness, multiplicity and evidence gates
      ↓
Personal research brief + provenance record
      ↓
Optional forward testing or pre-registered N-of-1 experiment

The research engine distinguishes association, directional evidence, forward-tested prediction, and randomized self-experiment evidence. Observational data alone does not establish causation.

Run locally

Requirements: Python 3.12 and pip. Docker Compose is an alternative.

git clone https://github.com/faruoqu146-ctrl/Nexgene_new_vision.git
cd Nexgene_new_vision

python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r backend/requirements.txt

Set a strong secret before starting the API:

export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

On Windows, set "SECRET_KEY" in the shell before running Uvicorn.

The API is available at "http://127.0.0.1:8000". FastAPI's interactive documentation is normally available at "/docs".

Docker Compose

export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose up --build

The Compose configuration uses persistent storage for its SQLite databases. Review "docker-compose.yml" before exposing the service or using real health data.

Do not enable development mode in a public deployment. Production requires secure configuration, persistent storage, and appropriately managed provider credentials.

Run tests

python -m pytest backend/tests -q

Run the bounded synthetic validation study:

python scripts/validation_study.py run --out validation_runs --budget 120
python scripts/validation_study.py report --out validation_runs

Tests and synthetic simulations can assess implementation behaviour under specified assumptions. They do not prove clinical usefulness, safety, causal validity, or performance on real-world patient data.

Repository map

Path| Purpose
"backend/app/main.py"| FastAPI routes, persistence, authentication, and application orchestration
"backend/app/research/"| Statistical research engine and evidence grading
"backend/app/governance/"| Consent and canonical observation contracts
"backend/tests/"| Unit, contract, security, isolation, and integration tests
"mobile/"| Lightweight browser-based interface
"scripts/"| Validation, demo data, and deterministic learning-cycle utilities
"knowledge/"| Evidence schema and example prior format
"docs/"| Architecture, phase specifications, acceptance criteria, and validation reports
".github/workflows/ci.yml"| Automated test and bounded-validation workflow
"Dockerfile", "docker-compose.yml"| Container build and local deployment

Current limitations

- No validated diagnostic or treatment recommendations.
- No evidence that research findings improve health outcomes.
- Clinical and genomic compartments are development foundations, not certified hospital integrations.
- Secondary research and cross-domain use require explicit purpose-specific consent; consent controls do not replace legal or ethics review.
- External evidence retrieval requires ongoing source-quality, caching, rate-limit, and provenance work.
- Production deployment requires independent security, privacy, operational, and clinical governance review.

Key documents

- "Phase 12 research engine" (docs/PHASE_12_RESEARCH_ENGINE.md)
- "Phase 12 validation report" (docs/PHASE_12_VALIDATION_REPORT.md)
- "Acceptance matrix" (docs/ACCEPTANCE_MATRIX.md)
- "Clinical compartment" (docs/PHASE_7_CLINICAL_COMPARTMENT.md)
- "Genomic and live-evidence foundation" (docs/PHASE_8_GENOMIC_LIVE_INTELLIGENCE.md)
- "Evidence pool design" (knowledge/README.md)

---

NexGene is being built around one rule: the strength of a health claim must never exceed the strength of its evidence.