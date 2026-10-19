"""Molecular domain consent and coverage."""
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


def _signal(code="marker_a", name="Marker A"):
    return {
        "marker_code": code,
        "marker_name": name,
        "result_mode": "deviation",
        "direction": "elevated",
        "significance": "mild",
        "confidence": 0.8,
    }


def test_biomarker_records_with_default_molecular_consent():
    r = ensure_user("mol-default@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/biomarkers/signals",
        json={"signals": [_signal()]},
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["data_domain"] == "molecular"
    assert "collect" in body["consent_purposes"]
    assert "personal_insight" in body["consent_purposes"]
    assert "research" not in body["consent_purposes"]


def test_biomarker_blocked_when_molecular_collect_revoked():
    r = ensure_user("mol-revoke@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    assert client.post(
        "/api/v1/biomarkers/signals",
        json={"signals": [_signal()]},
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200
    client.put(
        "/api/v1/consent",
        json={"purpose": "collect", "data_category": "molecular", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    blocked = client.post(
        "/api/v1/biomarkers/signals",
        json={"signals": [_signal("marker_b", "Marker B")]},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403


def test_molecular_coverage():
    r = ensure_user("mol-cov@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/biomarkers/signals",
        json={"signals": [_signal("crp", "CRP"), _signal("il6", "IL-6")]},
        headers={"X-CSRF-Token": csrf},
    )
    cov = client.get("/api/v1/molecular/coverage")
    assert cov.status_code == 200
    body = cov.json()
    assert body["data_domain"] == "molecular"
    assert body["signal_count"] >= 2
    assert body["claim_level"] == "descriptive_only"
    assert "collect" in body["consent_purposes"]
