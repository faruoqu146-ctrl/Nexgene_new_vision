# Restore backend/app/main.py

## Problem
An interrupted bulk push replaced `backend/app/main.py` with the literal string `PLACEHOLDER`.

## Fix (choose one)

### Option A — from last good commit then apply patch
```bash
git checkout 67ddcd29ef3a46ad39e14c80237161bfed8420d6 -- backend/app/main.py
patch -p0 < docs/patches/main_phase1.patch
git add backend/app/main.py
git commit -m "Restore main.py with Phase 1 auth/session fixes"
git push
```

### Option B — copy from a verified local tree
Use the working copy that passes:
`pytest backend/tests/test_security.py backend/tests/test_research_gates.py` (23 passed)

## Verify
```bash
export DEV_MODE=true SECRET_KEY=testsecretkeyfornexgene123456789012345
PYTHONPATH=. pytest backend/tests/test_security.py backend/tests/test_research_gates.py -q
```
