"""Integration tests for purpose-specific consent and canonical check-in fields."""
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


def test_default_lifestyle_consent_on_first_checkin():
    r = ensure_user("consent-checkin@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7, "sleep_duration": 7.5}},
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["saved"] == 2
    assert body["data_domain"] == "lifestyle"
    assert "collect" in body["consent_purposes"]
    assert "personal_insight" in body["consent_purposes"]


def test_get_consent_lists_defaults_after_checkin():
    r = ensure_user("consent-get@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 6}},
        headers={"X-CSRF-Token": csrf},
    )
    cons = client.get("/api/v1/consent")
    assert cons.status_code == 200
    data = cons.json()
    purposes = {c["purpose"]: c["granted"] for c in data["consents"]}
    assert purposes.get("collect") is True
    assert purposes.get("personal_insight") is True
    assert purposes.get("research") is not True


def test_revoke_collect_blocks_checkin():
    r = ensure_user("consent-revoke@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    # Seed defaults via check-in
    assert client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 5}},
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200
    # Revoke collect
    rev = client.put(
        "/api/v1/consent",
        json={"purpose": "collect", "data_category": "lifestyle", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert rev.status_code == 200
    assert rev.json()["granted"] is False
    blocked = client.post(
        "/api/v1/checkins/evening",
        json={"values": {"energy": 4}},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403


def test_unknown_purpose_rejected():
    r = ensure_user("consent-bad@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    bad = client.put(
        "/api/v1/consent",
        json={"purpose": "not_a_real_purpose", "granted": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert bad.status_code == 422
