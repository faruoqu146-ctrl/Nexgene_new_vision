"""Phase 3: genomic compartment dual-auth and isolation (parity with clinical)."""
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


def test_genomic_status_separate_store():
    r = ensure_user("genomic-status@example.com")
    assert r.status_code == 200
    out = client.get("/api/v1/genomics/status")
    assert out.status_code == 200
    body = out.json()
    assert body["compartment"] == "genomic"
    assert body["separate_store"] is True
    assert body["status"] == "not_authorized"
    assert body["grants"] == []


def test_genomic_user_consent_alone_not_dual_authorized():
    r = ensure_user("genomic-consent@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/genomics/consent",
        json={"provider_id": "development-genomics-provider", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200
    body = out.json()
    assert body["status"] == "user_authorized"
    assert body["dual_authorized"] is False


def test_genomic_data_empty_without_dual_auth():
    r = ensure_user("genomic-data@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/genomics/consent",
        json={"provider_id": "development-genomics-provider", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    data = client.get("/api/v1/genomics/data")
    assert data.status_code == 200
    body = data.json()
    assert body["status"] == "not_authorized"
    assert body["variants"] == []
    assert body["polygenic_scores"] == []


def test_genomic_grants_user_scoped():
    r1 = ensure_user("genomic-a@example.com")
    assert r1.status_code == 200
    csrf1 = r1.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/genomics/consent",
        json={"provider_id": "development-genomics-provider", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf1},
    )
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf1})
    r2 = ensure_user("genomic-b@example.com")
    assert r2.status_code == 200
    status = client.get("/api/v1/genomics/status")
    assert status.status_code == 200
    assert status.json()["grants"] == []


def test_genomic_provider_requires_configuration():
    out = client.post(
        "/api/v1/genomics/provider/grant",
        json={"provider_id": "development-genomics-provider", "subject_ref": "ngs_" + ("b" * 32)},
    )
    assert out.status_code in (401, 503)
