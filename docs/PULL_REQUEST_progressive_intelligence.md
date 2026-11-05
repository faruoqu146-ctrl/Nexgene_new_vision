# Progressive intelligence: immediate, honest feedback from the first check-in

## Why
Users got nothing back after a check-in, and the weekly report collapsed to "not enough data" until weeks of history existed. Worse, no evening check-in the UI could produce was accepted by the API (HTTP 422).

## What changed
- **Fix (blocking):** check-in validation rules extracted to `backend/app/checkin.py`; categorical answers (activity, eating, nicotine) are accepted as text, digit strings become numbers, `"skipped"` is not stored. Invalid values are still rejected.
- **New `backend/app/progressive.py`:** pure, deterministic, no model. L1 observations, L2 descriptive patterns (sample size on every item), L3 engine-only associations (+ progress to the engine's minimum pairs), L4 personal baseline (existing 7-vs-21-day method and gates reused).
- **API:** `save_checkin` returns `feedback` after commit (a feedback failure never fails the save); new `GET /api/v1/intelligence/progressive`; `/signals`, `/insights`, `/reports/weekly`, `/patterns` read from the same module and the same local-day boundaries. Weekly report gains an additive `layout` (contract `/1` unchanged).
- **UI:** `progressive-view.js`; saving/saved/error states in the sheet, Today updates from the save response without a reload, API failure is not drawn as an empty day, loading is not drawn as missing data, sparse Patterns and Report, collapsed missing-data details. Falls back to the old report rendering if the server has no `layout`.

## Not changed (deliberately)
No threshold lowered (guard test: 3 / 4 days, 14 / 21 pairs). No association is computed outside the research engine. No causal or diagnostic wording. Consent-compartment tables untouched. AI remains optional and reads the same deterministic sections. No deployment, no production data.

## Review these
1. `activity_level` / `diet_quality` / `nicotine` stay text; making them numeric 0-10 is a product decision.
2. Removed an over-claim in `/insights` ("enough data to start looking for relationships" from one reading) and a 4-pair sleep/focus hint in `/signals` (below every engine threshold).
3. `test_research_surface_contract` anchor updated (`loadSignals` no longer exists).

## Test results
- Python (stand-in unittest runner): 250 passed, 0 failed (204 existing + 46 new).
- JS: `node --test mobile/tests/*.test.js` 66 passed (44 existing + 22 new).
- Headless Chromium at 390 px against a stand-in API using the real `progressive.py`: 24/24 checks.
- **Not run (no network, deps not installable): FastAPI/SQLAlchemy/pytest.** `test_progressive_api.py` (new, 11 tests), `test_security.py`, `test_research_api.py`, `test_clinical_compartment.py` need a CI run before merge: `pip install -r backend/requirements.txt && pytest backend/tests && node --test mobile/tests/*.test.js`.

Full audit and root causes: `docs/PROGRESSIVE_INTELLIGENCE_REPORT.md`.
