"""Phase 3: clinical compartment dual-auth and isolation."""
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


def test_clinical_status_separate_store():
    r = ensure_user("clinical-status@example.com")
    assert r.status_code == 200
    out = client.get("/api/v1/clinical/status")
    assert out.status_code == 200
    body = out.json()
    assert body["compartment"] == "clinical"
    assert body["separate_store"] is True
    assert body["grants"] == []


def test_user_consent_alone_is_not_dual_authorized():
    r = ensure_user("clinical-consent@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/clinical/consent",
        json={"provider_id": "development-provider", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200
    body = out.json()
    assert body["status"] == "user_authorized"
    assert body["dual_authorized"] is False
    assert body["provider_authorized"] is False


def test_clinical_records_empty_without_dual_auth():
    r = ensure_user("clinical-records@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/clinical/consent",
        json={"provider_id": "development-provider", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    rows = client.get("/api/v1/clinical/records")
    assert rows.status_code == 200
    body = rows.json()
    if isinstance(body, list):
        assert body == []
    else:
        assert body.get("records", body.get("items", [])) == [] or body.get("count", 0) == 0


def test_clinical_grants_are_user_scoped():
    r1 = ensure_user("clinical-a@example.com")
    assert r1.status_code == 200
    csrf1 = r1.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/clinical/consent",
        json={"provider_id": "development-provider", "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf1},
    )
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf1})
    r2 = ensure_user("clinical-b@example.com")
    assert r2.status_code == 200
    status = client.get("/api/v1/clinical/status")
    assert status.status_code == 200
    assert status.json()["grants"] == []


def test_provider_endpoints_require_configuration():
    """Without CLINICAL_PROVIDER_KEY, provider routes must not be open."""
    out = client.post(
        "/api/v1/clinical/provider/grant",
        json={"provider_id": "development-provider", "subject_ref": "nxc_" + ("a" * 32)},
    )
    assert out.status_code in (401, 503)
