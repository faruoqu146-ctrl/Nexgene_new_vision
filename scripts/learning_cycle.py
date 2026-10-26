"""Recurring NexGene intelligence cycle.

Runs the deterministic personal baseline first, then the NexGene Research
Engine (calibrated inference, evidence tiers, locked-model forward tests). The
engine is intentionally structured and auditable rather than an LLM loop.

Schedule this worker externally in production.
"""
from sqlalchemy import select
import sys

from backend.app.main import INTELLIGENCE_MODEL_VERSION, SessionLocal, User, run_intelligence_engine, EngineBusy
from backend.app.main import LearningRun
from scripts.learning_cycle_legacy import run_for_user as run_baseline_for_user

MODEL_VERSION = INTELLIGENCE_MODEL_VERSION


def main():
    completed, skipped, failed = 0, 0, []
    with SessionLocal() as s:
        user_ids = [u.id for u in s.scalars(select(User)).all()]
        for uid in user_ids:
            user = s.get(User, uid)
            try:
                run_baseline_for_user(s, user)
                s.commit()
                run_intelligence_engine(user, s)
                completed += 1
            except EngineBusy:
                skipped += 1
            except Exception as exc:
                s.rollback()
                failed.append((uid, type(exc).__name__))
    print(f"completed {completed} NexGene intelligence cycles with {MODEL_VERSION}; skipped {skipped} busy; failed {len(failed)}")
    for uid, category in failed:
        print(f"  user {uid}: {category}", file=sys.stderr)
    if failed:
        sys.exit(1)

if __name__ == "__main__":
    main()
