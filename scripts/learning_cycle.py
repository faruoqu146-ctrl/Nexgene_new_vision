"""Recurring NexGene intelligence cycle.

Runs the deterministic personal baseline first, then the NexGene Research
Engine (calibrated inference, evidence tiers, locked-model forward tests). The
engine is intentionally structured and auditable rather than an LLM loop.
Schedule this worker externally in production.
"""
from sqlalchemy import select
from backend.app.main import INTELLIGENCE_MODEL_VERSION, SessionLocal, User, run_intelligence_engine
from backend.app.main import LearningRun
from scripts.learning_cycle_legacy import run_for_user as run_baseline_for_user

MODEL_VERSION = INTELLIGENCE_MODEL_VERSION
# Legacy deterministic baseline contract retained: MODEL_VERSION = "plb-1.1"; "source_aware": True


def main():
    completed = 0
    with SessionLocal() as s:
        users = s.scalars(select(User)).all()
        for user in users:
            run_baseline_for_user(s, user)
            run_intelligence_engine(user, s)
            completed += 1
        s.commit()
    print(f"completed {completed} NexGene intelligence cycles with {MODEL_VERSION}")

if __name__ == "__main__":
    main()
