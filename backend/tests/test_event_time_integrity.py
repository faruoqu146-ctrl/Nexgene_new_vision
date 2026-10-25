"""Temporal integrity: analysis must use event time (observed_at), not import time."""
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import os

# Force sqlite for tests
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/nexgene_test_event_time.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-event-time-suite")
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("COOKIE_SECURE", "false")

from backend.app.main import app, SessionLocal, Observation, User, event_time, now


def _client():
    return TestClient(app)


def test_event_time_prefers_observed_at():
    class R:
        observed_at = datetime(2026, 1, 10, tzinfo=timezone.utc)
        recorded_at = datetime(2026, 10, 25, tzinfo=timezone.utc)
    assert event_time(R()).date().isoformat() == "2026-01-10"


def test_event_time_falls_back_to_recorded_at():
    class R:
        observed_at = None
        recorded_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert event_time(R()).date().isoformat() == "2026-10-01"


def test_weekly_report_uses_event_window_not_import_time():
    c = _client()
    email = "event-time-tester@example.com"
    password = "secure-password-12"
    # register or login
    r = c.post("/api/v1/auth/register", json={"email": email, "password": password})
    if r.status_code >= 400:
        r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code < 400, r.text
    # csrf
    c.get("/api/v1/auth/csrf")
    csrf = c.cookies.get("nexgene_csrf")
    headers = {"X-CSRF-Token": csrf} if csrf else {}

    # Insert historical observation with observed_at 10 days ago, recorded_at = now
    s = SessionLocal()
    try:
        me = c.get("/api/v1/auth/me").json()
        uid = me["id"]
        # clear prior
        s.query(Observation).filter(Observation.user_id == uid).delete()
        s.commit()
        past = now() - timedelta(days=10)
        s.add(Observation(
            user_id=uid, kind="sleep_duration", value_numeric=7.5,
            recorded_at=now(), observed_at=past,
        ))
        s.add(Observation(
            user_id=uid, kind="focus", value_numeric=8,
            recorded_at=now(), observed_at=past,
        ))
        s.commit()
    finally:
        s.close()

    report = c.get("/api/v1/reports/weekly").json()
    # 10 days ago is outside the 7-day week window
    assert report.get("coverage", {}).get("days", 0) == 0 or report.get("status") == "not_ready", report

    # Observation 2 days ago should appear in week
    s = SessionLocal()
    try:
        me = c.get("/api/v1/auth/me").json()
        uid = me["id"]
        s.query(Observation).filter(Observation.user_id == uid).delete()
        s.commit()
        recent = now() - timedelta(days=2)
        s.add(Observation(
            user_id=uid, kind="sleep_duration", value_numeric=7.0,
            recorded_at=now(), observed_at=recent,
        ))
        s.commit()
    finally:
        s.close()

    report = c.get("/api/v1/reports/weekly").json()
    assert report.get("status") == "ready" or report.get("coverage", {}).get("days", 0) >= 1, report
    assert report.get("coverage", {}).get("observations", 0) >= 1
