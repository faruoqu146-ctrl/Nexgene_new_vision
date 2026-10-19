"""Physiological domain tagging and coverage (descriptive only)."""
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


def test_physiological_kinds_tagged_on_checkin():
    r = ensure_user("physio-tag@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/checkins/morning",
        json={"values": {"heart_rate": 72, "hrv": 40}},
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["data_domain"] == "physiological"
    assert "physiological" in body["data_domains"]


def test_mixed_checkin_reports_mixed_domain():
    r = ensure_user("physio-mixed@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7, "heart_rate": 70}},
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200
    body = out.json()
    assert body["data_domain"] == "mixed"
    assert "lifestyle" in body["data_domains"]
    assert "physiological" in body["data_domains"]


def test_physiological_coverage():
    r = ensure_user("physio-cov@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"weight": 70.5, "glucose": 95.0}},
        headers={"X-CSRF-Token": csrf},
    )
    cov = client.get("/api/v1/physiological/coverage")
    assert cov.status_code == 200
    body = cov.json()
    assert body["data_domain"] == "physiological"
    assert body["claim_level"] == "descriptive_only"
    assert body["observation_count"] >= 2
    assert "weight" in body["variables"] or "glucose" in body["variables"]
