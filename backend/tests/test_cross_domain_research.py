"""Cross-domain and secondary research purpose gates."""
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


def test_secondary_research_denied_by_default():
    r = ensure_user("research-default@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7}},
        headers={"X-CSRF-Token": csrf},
    )
    out = client.get("/api/v1/research/secondary-use-status")
    assert out.status_code == 200
    body = out.json()
    assert body["secondary_research_authorized"] is False
    assert body["required_purpose"] == "research"
    assert "collect" in body["granted_lifestyle"]
    assert "research" not in body["granted_lifestyle"]


def test_secondary_research_after_grant():
    r = ensure_user("research-grant@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 7}},
        headers={"X-CSRF-Token": csrf},
    )
    client.put(
        "/api/v1/consent",
        json={"purpose": "research", "data_category": "lifestyle", "granted": True},
        headers={"X-CSRF-Token": csrf},
    )
    out = client.get("/api/v1/research/secondary-use-status")
    assert out.status_code == 200
    assert out.json()["secondary_research_authorized"] is True


def test_intelligence_brief_without_cross_domain_does_not_include_clinical_records():
    """Without cross_domain, clinical_context must not report authorized records."""
    r = ensure_user("cross-domain@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 6}},
        headers={"X-CSRF-Token": csrf},
    )
    brief = client.get("/api/v1/intelligence/brief")
    assert brief.status_code == 200
    body = brief.json()
    assert body.get("clinical_context", {}).get("status") in (
        "not_authorized",
        "unavailable",
        "blocked_missing_cross_domain_consent",
    )
    assert body.get("clinical_context", {}).get("record_count", 0) == 0
