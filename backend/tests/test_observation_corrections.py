"""Observation correction history (supersedes) and research panel exclusion."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from backend.app.main import app, SessionLocal, Observation, User, _research_panel
from sqlalchemy import select

client = TestClient(app)


def ensure_user(email, password="A_secure_password!9"):
    payload = {"email": email, "password": password}
    r = client.post("/api/v1/auth/register", json=payload)
    if r.status_code not in (200, 409):
        return r
    return client.post("/api/v1/auth/login", json=payload)


def test_correction_marks_prior_superseded_and_panel_uses_corrected():
    r = ensure_user("corr@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    first = client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "energy", "value": 5, "source_type": "user-entered"}]},
        headers={"X-CSRF-Token": csrf},
    )
    assert first.status_code == 200, first.text
    s = SessionLocal()
    try:
        u = s.scalar(select(User).where(User.email == "corr@example.com"))
        prior = s.scalars(select(Observation).where(Observation.user_id == u.id, Observation.kind == "energy")).first()
        prior_id = prior.id
    finally:
        s.close()

    corr = client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "energy", "value": 8, "source_type": "user-entered", "supersedes_observation_id": prior_id}]},
        headers={"X-CSRF-Token": csrf},
    )
    assert corr.status_code == 200, corr.text
    assert corr.json()["corrections"] == 1

    s = SessionLocal()
    try:
        u = s.scalar(select(User).where(User.email == "corr@example.com"))
        prior = s.get(Observation, prior_id)
        assert prior.quality_flag == "superseded"
        panel, rows, _, _ = _research_panel(u, s, window_days=30)
        energy_vals = [r.value_numeric for r in rows if r.kind == "energy"]
        assert 5.0 not in energy_vals
        assert 8.0 in energy_vals
    finally:
        s.close()


def test_correction_wrong_kind_rejected():
    r = ensure_user("corr-kind@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "energy", "value": 4}]},
        headers={"X-CSRF-Token": csrf},
    )
    s = SessionLocal()
    try:
        u = s.scalar(select(User).where(User.email == "corr-kind@example.com"))
        prior_id = s.scalars(select(Observation).where(Observation.user_id == u.id)).first().id
    finally:
        s.close()
    bad = client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "stress", "value": 3, "supersedes_observation_id": prior_id}]},
        headers={"X-CSRF-Token": csrf},
    )
    assert bad.status_code == 400
