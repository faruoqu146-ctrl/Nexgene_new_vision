"""Inspectable research panel domain composition."""
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


def test_panel_domains_endpoint_reports_consent_and_exclusion():
    r = ensure_user("domains-api@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7}},
        headers={"X-CSRF-Token": csrf},
    )
    client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "air_quality_index", "value": 40, "source_type": "environmental"}]},
        headers={"X-CSRF-Token": csrf},
    )
    ok = client.get("/api/v1/intelligence/panel/domains")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["consent"]["lifestyle_personal_insight"] is True
    assert body["consent"]["environmental_personal_insight"] is True

    client.put(
        "/api/v1/consent",
        json={"purpose": "personal_insight", "data_category": "environmental", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    blocked = client.get("/api/v1/intelligence/panel/domains")
    assert blocked.status_code == 200
    b2 = blocked.json()
    assert b2["consent"]["environmental_personal_insight"] is False
    assert b2["excluded_for_consent"]["environmental"] >= 1
    assert "air_quality_index" not in b2["included"]["variables"]


def test_panel_domains_requires_lifestyle_personal_insight():
    r = ensure_user("domains-deny@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.put(
        "/api/v1/consent",
        json={"purpose": "personal_insight", "data_category": "lifestyle", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    resp = client.get("/api/v1/intelligence/panel/domains")
    assert resp.status_code == 403
