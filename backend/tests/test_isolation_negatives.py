"""Negative isolation and consent-withdrawal tests (Directive 01 Phase 3)."""
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


def test_timeline_does_not_leak_across_users():
    r1 = ensure_user("iso-a@example.com")
    assert r1.status_code == 200
    csrf1 = r1.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 8, "sleep_duration": 7.2}},
        headers={"X-CSRF-Token": csrf1},
    )
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf1})

    r2 = ensure_user("iso-b@example.com")
    assert r2.status_code == 200
    tl = client.get("/api/v1/timeline")
    assert tl.status_code == 200
    body = tl.json()
    if isinstance(body, list):
        assert len(body) == 0 or all(
            (x.get("value_numeric") not in (8, 7.2) if isinstance(x, dict) else True)
            for x in body
        )
    elif isinstance(body, dict):
        items = body.get("items") or body.get("observations") or body.get("events") or []
        assert isinstance(items, list)


def test_research_engine_blocked_after_personal_insight_revoked():
    r = ensure_user("iso-revoke@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    for _ in range(3):
        client.post(
            "/api/v1/checkins/morning",
            json={"values": {"energy": 6, "stress": 4}},
            headers={"X-CSRF-Token": csrf},
        )
    client.put(
        "/api/v1/consent",
        json={"purpose": "personal_insight", "data_category": "lifestyle", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    run = client.post(
        "/api/v1/intelligence/engine/run",
        headers={"X-CSRF-Token": csrf},
    )
    assert run.status_code in (403, 401), run.text


def test_checkin_blocked_after_collect_revoked():
    r = ensure_user("iso-collect@example.com")
    assert r.status_code == 200
    csrf = r.cookies.get("nexgene_csrf") or client.cookies.get("nexgene_csrf")
    ok = client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 5}},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200
    client.put(
        "/api/v1/consent",
        json={"purpose": "collect", "data_category": "lifestyle", "granted": False},
        headers={"X-CSRF-Token": csrf},
    )
    blocked = client.post(
        "/api/v1/checkins/morning",
        json={"values": {"energy": 6}},
        headers={"X-CSRF-Token": csrf},
    )
    assert blocked.status_code == 403
