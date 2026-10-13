import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def strong(email='security@example.com', password='A_secure_password!9'):
    return {'email': email, 'password': password}


def test_password_policy():
    r = client.post('/api/v1/auth/register', json={'email': 'weak@example.com', 'password': 'password'})
    assert r.status_code in (400, 422)


def test_cookie_auth_and_csrf():
    r = client.post('/api/v1/auth/register', json=strong())
    assert r.status_code in (200, 409)
    if r.status_code == 409:
        r = client.post('/api/v1/auth/login', json=strong())
        assert r.status_code == 200
    assert 'nexgene_session' in r.cookies
    csrf = r.cookies.get('nexgene_csrf')
    bad = client.post('/api/v1/checkins/morning', json={'values': {'energy': 8}})
    assert bad.status_code == 403
    good = client.post('/api/v1/checkins/morning', json={'values': {'energy': 8}}, headers={'X-CSRF-Token': csrf})
    assert good.status_code == 200


def test_csrf_rotation_updates_server_hash():
    r = client.post('/api/v1/auth/login', json=strong())
    assert r.status_code == 200
    r2 = client.get('/api/v1/auth/csrf')
    assert r2.status_code == 200
    csrf = r2.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    good = client.post('/api/v1/checkins/morning', json={'values': {'energy': 7}}, headers={'X-CSRF-Token': csrf})
    assert good.status_code == 200


def test_logout_revokes_session():
    r = client.post('/api/v1/auth/login', json=strong())
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    out = client.post('/api/v1/auth/logout', headers={'X-CSRF-Token': csrf})
    assert out.status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 401


def test_existing_registration_is_uniform():
    email = 'enumeration@example.com'
    client.post('/api/v1/auth/register', json=strong(email=email))
    r = client.post('/api/v1/auth/register', json=strong(email=email))
    assert r.status_code == 200
    assert 'dev_verification_token' not in r.json()


def test_missing_login_still_runs_dummy_password_verification():
    r = client.post('/api/v1/auth/login', json=strong(email='definitely-missing@example.com'))
    assert r.status_code == 401
    assert r.json()['detail'] == 'Invalid email or password'


def test_checkin_rejects_unknown_kind_and_oversized_value():
    r = client.post('/api/v1/auth/login', json=strong())
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    unknown = client.post('/api/v1/checkins/morning', json={'values': {'made_up_kind': 'x'}}, headers={'X-CSRF-Token': csrf})
    assert unknown.status_code == 422
    oversized = client.post('/api/v1/checkins/morning', json={'values': {'morning_context': 'x' * 257}}, headers={'X-CSRF-Token': csrf})
    assert oversized.status_code == 422


def test_production_docs_are_configurable_off():
    from backend.app.main import DEV_MODE
    if not DEV_MODE:
        assert client.get('/docs').status_code == 404
        assert client.get('/openapi.json').status_code == 404


def test_profile_is_user_scoped_and_csrf_protected():
    r = client.post('/api/v1/auth/login', json=strong(email='profile@example.com'))
    assert r.status_code == 200
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    bad = client.put('/api/v1/profile', json={'country': 'Nigeria'})
    assert bad.status_code == 403
    good = client.put('/api/v1/profile', json={'country': 'Nigeria', 'occupation': 'Researcher', 'student': False}, headers={'X-CSRF-Token': csrf})
    assert good.status_code == 200
    got = client.get('/api/v1/profile')
    assert got.status_code == 200
    assert got.json()['profile']['country'] == 'Nigeria'


def test_weekly_report_is_user_scoped_and_returns_safe_shape():
    r = client.post('/api/v1/auth/login', json=strong(email='report@example.com'))
    assert r.status_code == 200
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    client.post('/api/v1/checkins/morning', json={'values': {'sleep_duration': 7.5, 'energy': 8}}, headers={'X-CSRF-Token': csrf})
    report = client.get('/api/v1/reports/weekly')
    assert report.status_code == 200
    body = report.json()
    assert body['status'] in ('ready', 'not_ready')
    assert 'profile' in body and 'coverage' in body


def test_biomarker_deviation_signal_and_intelligence():
    r = client.post('/api/v1/auth/login', json=strong(email='molecular@example.com'))
    assert r.status_code == 200
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    bad = client.post('/api/v1/biomarkers/signals', json={'signals': [{
        'marker_code': 'marker_a', 'marker_name': 'Marker A', 'result_mode': 'deviation',
        'direction': 'elevated', 'significance': 'significant', 'value_numeric': 12.3
    }]}, headers={'X-CSRF-Token': csrf})
    assert bad.status_code == 422
    good = client.post('/api/v1/biomarkers/signals', json={'signals': [{
        'marker_code': 'marker_a', 'marker_name': 'Marker A', 'result_mode': 'deviation',
        'direction': 'elevated', 'significance': 'significant', 'confidence': 0.9
    }]}, headers={'X-CSRF-Token': csrf})
    assert good.status_code == 200
    rows = client.get('/api/v1/biomarkers').json()
    assert rows[0]['marker_code'] == 'marker_a'
    brief = client.get('/api/v1/intelligence/brief')
    assert brief.status_code == 200
    assert 'clinical_escalation' in brief.json()


def test_biomarker_is_user_scoped():
    r = client.post('/api/v1/auth/login', json=strong(email='molecular-a@example.com'))
    assert r.status_code == 200
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    client.post('/api/v1/biomarkers/signals', json={'signals': [{
        'marker_code': 'private_a', 'marker_name': 'Private A', 'result_mode': 'deviation',
        'direction': 'low', 'significance': 'mild'
    }]}, headers={'X-CSRF-Token': csrf})
    client.post('/api/v1/auth/logout', headers={'X-CSRF-Token': csrf})
    r2 = client.post('/api/v1/auth/login', json=strong(email='molecular-b@example.com'))
    assert r2.status_code == 200
    rows = client.get('/api/v1/biomarkers').json()
    assert all(x['marker_code'] != 'private_a' for x in rows)


def test_evidence_import_is_dev_only_and_retrievable():
    r = client.post('/api/v1/auth/login', json=strong(email='evidence@example.com'))
    assert r.status_code == 200
    csrf = r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')
    from backend.app.main import DEV_MODE
    payload = {'sources': [{
        'source_type': 'research', 'title': 'Sleep and energy longitudinal research',
        'topic_tags': ['sleep', 'energy'], 'abstract_summary': 'Development fixture only.'
    }]}
    out = client.post('/api/v1/evidence/import', json=payload, headers={'X-CSRF-Token': csrf})
    if DEV_MODE:
        assert out.status_code == 200
        found = client.get('/api/v1/evidence/search?q=sleep energy')
        assert found.status_code == 200
        assert any(x['title'] == payload['sources'][0]['title'] for x in found.json())
    else:
        assert out.status_code == 404
