"""Research panel includes only consent-eligible domains."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from backend.app.main import app, SessionLocal, _research_panel, User
from sqlalchemy import select

client = TestClient(app)


def ensure_user(email, password="A_secure_password!9"):
    payload = {"email": email, "password": password}
    r = client.post("/api/v1/auth/register", json=payload)
    if r.status_code not in (200, 409):
        return r
    return client.post("/api/v1/auth/login", json=payload)


def test_environmental_excluded_without_personal_insight():
    r = ensure_user("panel-env@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7, "stress": 4}},
        headers={"X-CSRF-Token": csrf},
    )
    client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "air_quality_index", "value": 50, "source_type": "environmental"}]},
        headers={"X-CSRF-Token": csrf},
    )
    client.put(
        "/api/v1/consent",
        json={"purpose": "personal_insight", "data_category": "environmental", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )

    s = SessionLocal()
    try:
        u = s.scalar(select(User).where(User.email == "panel-env@example.com"))
        assert u is not None
        panel, rows, _ = _research_panel(u, s, window_days=30)
        kinds = {r.kind for r in rows}
        assert "energy" in kinds or "stress" in kinds
        assert "air_quality_index" not in kinds
        assert "air_quality_index" not in panel.variables
    finally:
        s.close()


def test_environmental_included_with_personal_insight():
    r = ensure_user("panel-env-ok@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 6}},
        headers={"X-CSRF-Token": csrf},
    )
    client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "pollen_index", "value": 4, "source_type": "environmental"}]},
        headers={"X-CSRF-Token": csrf},
    )
    s = SessionLocal()
    try:
        u = s.scalar(select(User).where(User.email == "panel-env-ok@example.com"))
        panel, rows, _ = _research_panel(u, s, window_days=30)
        kinds = {r.kind for r in rows}
        assert "pollen_index" in kinds
        assert "pollen_index" in panel.variables
    finally:
        s.close()
