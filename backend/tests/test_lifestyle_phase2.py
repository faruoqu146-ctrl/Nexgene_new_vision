"""Lifestyle completion: baselines + intelligence consent gate."""
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


def test_lifestyle_baselines_descriptive():
    r = ensure_user("baseline@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    for energy in (6, 7, 8, 5, 7):
        client.post(
            "/api/v1/checkins/morning",
            json={"values": {"energy": energy}},
            headers={"X-CSRF-Token": csrf},
        )
    out = client.get("/api/v1/lifestyle/baselines")
    assert out.status_code == 200
    body = out.json()
    assert body["status"] == "ready"
    assert body["data_domain"] == "lifestyle"
    kinds = {v["kind"]: v for v in body["variables"]}
    assert "energy" in kinds
    assert kinds["energy"]["n"] >= 5
    assert kinds["energy"]["claim_level"] == "descriptive_only"


def test_intelligence_requires_personal_insight():
    r = ensure_user("intel-consent@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    # Seed defaults via check-in
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7}},
        headers={"X-CSRF-Token": csrf},
    )
    # Revoke personal_insight
    rev = client.put(
        "/api/v1/consent",
        json={"purpose": "personal_insight", "data_category": "lifestyle", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert rev.status_code == 200
    blocked = client.post(
        "/api/v1/intelligence/engine/run",
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403
