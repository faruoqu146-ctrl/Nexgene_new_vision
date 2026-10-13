import os

os.environ.setdefault("CLINICAL_PROVIDER_KEY", "test-provider-key")

from fastapi.testclient import TestClient
from backend.app.main import app, CLINICAL_PROVIDER_ID

client = TestClient(app)

def strong(email="clinical@example.com"):
    return {"email": email, "password": "StrongPassword9!"}

def csrf():
    r = client.get("/api/v1/auth/csrf")
    return r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")

def login(email):
    r = client.post("/api/v1/auth/login", json=strong(email))
    assert r.status_code == 200
    return r

def test_clinical_requires_dual_authorization():
    email = "dual@example.com"
    client.post("/api/v1/auth/register", json=strong(email))
    login(email)
    token = csrf()
    consent = client.post("/api/v1/clinical/consent", json={"provider_id": CLINICAL_PROVIDER_ID, "scopes": ["read"]}, headers={"X-CSRF-Token": token})
    assert consent.status_code == 200
    subject_ref = consent.json()["subject_ref"]
    blocked = client.get("/api/v1/clinical/records")
    assert blocked.status_code == 200 and blocked.json()["status"] == "not_authorized"
    provider = {"X-Clinical-Provider-Key": "test-provider-key"}
    grant = client.post("/api/v1/clinical/provider/grant", json={"subject_ref": subject_ref, "provider_id": CLINICAL_PROVIDER_ID}, headers=provider)
    assert grant.status_code == 200 and grant.json()["dual_authorized"] is True
    sync = client.post("/api/v1/clinical/provider/records", json={"records": [{
        "subject_ref": subject_ref, "provider_id": CLINICAL_PROVIDER_ID, "record_type": "lab",
        "display": "HbA1c", "status": "final", "summary": "Clinical test result", "payload": {"value": 5.4, "unit": "%"}
    }]}, headers=provider)
    assert sync.status_code == 200
    records = client.get("/api/v1/clinical/records")
    assert records.status_code == 200
    assert records.json()["status"] == "authorized"
    assert records.json()["records"][0]["record_type"] == "lab"

def test_clinical_revocation_removes_access():
    email = "revoke@example.com"
    client.post("/api/v1/auth/register", json=strong(email))
    login(email)
    token = csrf()
    consent = client.post("/api/v1/clinical/consent", json={"provider_id": CLINICAL_PROVIDER_ID}, headers={"X-CSRF-Token": token})
    ref = consent.json()["subject_ref"]
    provider = {"X-Clinical-Provider-Key": "test-provider-key"}
    assert client.post("/api/v1/clinical/provider/grant", json={"subject_ref": ref, "provider_id": CLINICAL_PROVIDER_ID}, headers=provider).status_code == 200
    assert client.post("/api/v1/clinical/provider/records", json={"records": [{"subject_ref": ref, "provider_id": CLINICAL_PROVIDER_ID, "record_type": "diagnosis", "display": "Example", "payload": {}}]}, headers=provider).status_code == 200
    assert client.get("/api/v1/clinical/records").json()["status"] == "authorized"
    revoked = client.post(f"/api/v1/clinical/revoke?provider_id={CLINICAL_PROVIDER_ID}", headers={"X-CSRF-Token": token})
    assert revoked.status_code == 200
    assert client.get("/api/v1/clinical/records").json()["status"] == "not_authorized"

def test_provider_cannot_sync_without_user_consent():
    provider = {"X-Clinical-Provider-Key": "test-provider-key"}
    out = client.post("/api/v1/clinical/provider/records", json={"records": [{"subject_ref": "nxc_unconsented_subject_123456789", "provider_id": CLINICAL_PROVIDER_ID, "record_type": "lab", "display": "Blocked", "payload": {}}]}, headers=provider)
    assert out.status_code == 403
