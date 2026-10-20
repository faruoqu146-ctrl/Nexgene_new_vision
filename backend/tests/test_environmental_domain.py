"""Environmental domain + multi-domain observation batch."""
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


def test_environmental_batch_and_coverage():
    r = ensure_user("env-batch@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/observations/batch",
        json={
            "items": [
                {"kind": "air_quality_index", "value": 42, "source_type": "environmental"},
                {"kind": "pollen_index", "value": 3, "source_type": "environmental"},
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["data_domain"] == "environmental"
    assert body["claim_level"] == "descriptive_only"
    cov = client.get("/api/v1/environmental/coverage")
    assert cov.status_code == 200
    c = cov.json()
    assert c["observation_count"] >= 2
    assert c["data_domain"] == "environmental"


def test_wearable_physiological_batch():
    r = ensure_user("physio-wear@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/observations/batch",
        json={
            "items": [
                {"kind": "heart_rate", "value": 68, "source_type": "wearable", "quality_flag": "device_reported"},
                {"kind": "hrv", "value": 45, "source_type": "wearable", "quality_flag": "device_reported"},
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200, out.text
    body = out.json()
    assert body["data_domain"] == "physiological"
    assert "physiological" in body["data_domains"]


def test_mixed_lifestyle_environmental_batch():
    r = ensure_user("mixed-env@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    out = client.post(
        "/api/v1/observations/batch",
        json={
            "items": [
                {"kind": "energy", "value": 7, "source_type": "user-entered"},
                {"kind": "uv_index", "value": 6, "source_type": "environmental"},
            ]
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert out.status_code == 200, out.text
    assert out.json()["data_domain"] == "mixed"


def test_environmental_collect_revoke_blocks_batch():
    r = ensure_user("env-revoke@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    assert client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "noise_level", "value": 55, "source_type": "environmental"}]},
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200
    client.put(
        "/api/v1/consent",
        json={"purpose": "collect", "data_category": "environmental", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    blocked = client.post(
        "/api/v1/observations/batch",
        json={"items": [{"kind": "noise_level", "value": 60, "source_type": "environmental"}]},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403
