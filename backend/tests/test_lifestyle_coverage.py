"""Lifestyle coverage / completion gate tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def ensure_user(email, password="A_secure_password!9"):
    payload = {"email": email, "password": password}
    r = client.post("/api/v1/auth/register", json=payload)
    if r.status_code not in (200, 409):
        return r
    return client.post("/api/v1/auth/login", json=payload)


def test_coverage_not_ready_without_data():
    r = ensure_user("coverage-empty@example.com")
    assert r.status_code == 200
    out = client.get("/api/v1/lifestyle/coverage")
    assert out.status_code == 200
    body = out.json()
    assert body["lifestyle_layer_ready"] is False
    assert body["criteria"]["has_observations"] is False


def test_coverage_tracks_checkins_and_consent():
    r = ensure_user("coverage-ready@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7, "sleep_duration": 7.0}},
        headers={"X-CSRF-Token": csrf},
    )
    out = client.get("/api/v1/lifestyle/coverage")
    assert out.status_code == 200
    body = out.json()
    assert body["criteria"]["has_observations"] is True
    assert body["criteria"]["multi_variable"] is True
    assert body["criteria"]["consent_collect"] is True
    assert body["criteria"]["consent_personal_insight"] is True
    # Single day is not enough for 7-day criterion
    assert body["criteria"]["active_days_ge_7"] is False
    assert body["lifestyle_layer_ready"] is False


def test_research_brief_requires_personal_insight():
    r = ensure_user("brief-consent@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 6}},
        headers={"X-CSRF-Token": csrf},
    )
    client.put(
        "/api/v1/consent",
        json={"purpose": "personal_insight", "data_category": "lifestyle", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    blocked = client.get("/api/v1/intelligence/research/brief")
    assert blocked.status_code == 403
