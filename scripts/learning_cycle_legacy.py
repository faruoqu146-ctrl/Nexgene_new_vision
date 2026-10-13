"""Legacy deterministic personal baseline worker retained as a substrate."""
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from backend.app.main import SessionLocal, User, Observation, BiomarkerSignal, LearningRun
MODEL_VERSION = "plb-1.1"
WINDOW_DAYS = 90
def run_for_user(s, user):
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=WINDOW_DAYS)
    rows = s.scalars(select(Observation).where(Observation.user_id == user.id, Observation.recorded_at >= since)).all()
    nums = defaultdict(list)
    for row in rows:
        if row.value_numeric is not None:
            nums[row.kind].append(float(row.value_numeric))
    biomarkers = s.scalars(select(BiomarkerSignal).where(BiomarkerSignal.user_id == user.id, BiomarkerSignal.recorded_at >= since)).all()
    baselines = {}
    for kind, values in nums.items():
        if len(values) >= 3:
            baselines[kind] = {"n": len(values), "mean": round(sum(values) / len(values), 4), "min": round(min(values), 4), "max": round(max(values), 4)}
    artifact = {"model_family": "personal-longitudinal-baseline", "model_version": MODEL_VERSION, "window_days": WINDOW_DAYS, "observation_count": len(rows), "biomarker_count": len(biomarkers), "baselines": baselines, "generated_at": now.isoformat(), "method": "deterministic_personal_baseline", "source_aware": True}
    s.add(LearningRun(user_id=user.id, model_family=artifact["model_family"], model_version=MODEL_VERSION, status="completed", input_window_days=WINDOW_DAYS, output_json=json.dumps(artifact)))
    return artifact
