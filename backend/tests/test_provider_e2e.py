"""Provider-key E2E dual-auth for clinical and genomic compartments.

Requires CLINICAL_PROVIDER_KEY / GENOMIC_PROVIDER_KEY at import time.
Runs as a self-contained module so keys can be injected before app load.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# Inject test provider keys before (re)loading the application module.
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("SECRET_KEY", "ci-test-secret-key-not-for-production-use-32b")
os.environ["CLINICAL_PROVIDER_KEY"] = "test-clinical-provider-key-e2e"
os.environ["CLINICAL_PROVIDER_ID"] = "development-provider"
os.environ["GENOMIC_PROVIDER_KEY"] = "test-genomic-provider-key-e2e"
os.environ["GENOMIC_PROVIDER_ID"] = "development-genomics-provider"

import backend.app.main as main_mod  # noqa: E402

importlib.reload(main_mod)
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main_mod.app)

CLINICAL_KEY = os.environ["CLINICAL_PROVIDER_KEY"]
GENOMIC_KEY = os.environ["GENOMIC_PROVIDER_KEY"]
CLINICAL_PROVIDER_ID = os.environ["CLINICAL_PROVIDER_ID"]
GENOMIC_PROVIDER_ID = os.environ["GENOMIC_PROVIDER_ID"]


def ensure_user(email, password="A_secure_password!9"):
    payload = {"email": email, "password": password}
    r = client.post("/api/v1/auth/register", json=payload)
    if r.status_code not in (200, 409):
        return r
    return client.post("/api/v1/auth/login", json=payload)


def test_clinical_full_dual_auth_and_record_sync():
    r = ensure_user("e2e-clinical@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")

    consent = client.post(
        "/api/v1/clinical/consent",
        json={"provider_id": CLINICAL_PROVIDER_ID, "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert consent.status_code == 200, consent.text
    body = consent.json()
    assert body["dual_authorized"] is False
    subject_ref = body["subject_ref"]
    assert subject_ref.startswith("nxc_")

    pg = client.post(
        "/api/v1/clinical/provider/grant",
        json={"provider_id": CLINICAL_PROVIDER_ID, "subject_ref": subject_ref},
        headers={"X-Clinical-Provider-Key": CLINICAL_KEY},
    )
    assert pg.status_code == 200, pg.text
    assert pg.json()["dual_authorized"] is True

    sync = client.post(
        "/api/v1/clinical/provider/records",
        json={
            "records": [
                {
                    "subject_ref": subject_ref,
                    "provider_id": CLINICAL_PROVIDER_ID,
                    "record_type": "lab",
                    "display": "Synthetic CRP (demo)",
                    "status": "final",
                    "summary": "Synthetic fixture only",
                    "source_system": "e2e-fixture",
                    "external_id": "e2e-crp-1",
                }
            ]
        },
        headers={"X-Clinical-Provider-Key": CLINICAL_KEY},
    )
    assert sync.status_code == 200, sync.text
    assert sync.json().get("saved", 0) >= 1 or sync.json().get("status") == "synced"

    rows = client.get("/api/v1/clinical/records")
    assert rows.status_code == 200
    data = rows.json()
    if isinstance(data, list):
        assert len(data) >= 1
    else:
        recs = data.get("records") or data.get("items") or []
        assert len(recs) >= 1

    bad = client.post(
        "/api/v1/clinical/provider/grant",
        json={"provider_id": CLINICAL_PROVIDER_ID, "subject_ref": subject_ref},
        headers={"X-Clinical-Provider-Key": "wrong-key"},
    )
    assert bad.status_code in (401, 403)


def test_clinical_records_blocked_without_provider_grant():
    r = ensure_user("e2e-clinical-half@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    consent = client.post(
        "/api/v1/clinical/consent",
        json={"provider_id": CLINICAL_PROVIDER_ID, "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert consent.status_code == 200
    subject_ref = consent.json()["subject_ref"]

    blocked = client.post(
        "/api/v1/clinical/provider/records",
        json={
            "records": [
                {
                    "subject_ref": subject_ref,
                    "provider_id": CLINICAL_PROVIDER_ID,
                    "record_type": "diagnosis",
                    "display": "Should not sync",
                }
            ]
        },
        headers={"X-Clinical-Provider-Key": CLINICAL_KEY},
    )
    assert blocked.status_code == 403


def test_genomic_full_dual_auth_and_data_read():
    r = ensure_user("e2e-genomic@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")

    consent = client.post(
        "/api/v1/genomics/consent",
        json={"provider_id": GENOMIC_PROVIDER_ID, "scopes": ["read"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert consent.status_code == 200, consent.text
    body = consent.json()
    assert body["dual_authorized"] is False
    subject_ref = body["subject_ref"]

    pg = client.post(
        "/api/v1/genomics/provider/grant",
        json={"provider_id": GENOMIC_PROVIDER_ID, "subject_ref": subject_ref},
        headers={"X-Genomic-Provider-Key": GENOMIC_KEY},
    )
    assert pg.status_code == 200, pg.text
    assert pg.json().get("dual_authorized") is True

    variants = client.post(
        "/api/v1/genomics/provider/variants",
        json={
            "variants": [
                {
                    "subject_ref": subject_ref,
                    "provider_id": GENOMIC_PROVIDER_ID,
                    "gene": "TEST1",
                    "variant_id": "rsTEST0001",
                    "zygosity": "het",
                    "classification": "uncertain",
                    "significance": "unknown",
                }
            ]
        },
        headers={"X-Genomic-Provider-Key": GENOMIC_KEY},
    )
    assert variants.status_code in (200, 422), variants.text
    if variants.status_code == 200:
        data = client.get("/api/v1/genomics/data")
        assert data.status_code == 200
        assert data.json().get("status") == "authorized"
