"""API-level tests for progressive intelligence (needs the real FastAPI/SQLAlchemy stack, like test_security.py).

Users are created once per module (registration is rate-limited per IP) and each test uses its own user so
tests are independent of execution order.
"""
import json
import sys
import uuid
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pytest
from fastapi.testclient import TestClient
import backend.app.main as main_module
from backend.app.main import app

PASSWORD = 'A_secure_password!9'
RUN = uuid.uuid4().hex[:8]   # fresh accounts every run: the dev database persists, and day counts must start at zero


@pytest.fixture(autouse=True, scope='module')
def relaxed_registration_limit():
    """Registration is rate-limited per IP per minute (10). This module needs ~10 accounts, so lift the limit for it only."""
    original = main_module.MAX_REGISTER_ATTEMPTS
    main_module.MAX_REGISTER_ATTEMPTS = 1000
    yield
    main_module.MAX_REGISTER_ATTEMPTS = original


@lru_cache(maxsize=None)
def user(name):
    """Return (client, csrf) for a registered user. Each user has its own cookie jar."""
    client = TestClient(app)
    r = client.post('/api/v1/auth/register', json={'email': f'{name}.{RUN}@progressive.example.com', 'password': PASSWORD})
    if r.status_code != 200 or 'nexgene_csrf' not in r.cookies:
        r = client.post('/api/v1/auth/login', json={'email': f'{name}.{RUN}@progressive.example.com', 'password': PASSWORD})
    assert r.status_code == 200
    return client, (r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf'))


def checkin(name, period, values):
    client, csrf = user(name)
    return client.post(f'/api/v1/checkins/{period}', json={'values': values}, headers={'X-CSRF-Token': csrf})


MORNING = {'sleep_duration': 6.5, 'sleep_quality': 6, 'energy': 8}
# exactly what the mobile UI sends for an evening check-in (categorical answers stay text, counts are numbers)
EVENING_UI = {'mood': 8, 'stress': 3, 'focus': 6, 'activity_level': 'light', 'diet_quality': 'good', 'caffeine': 1, 'alcohol': 0, 'nicotine': 'none'}


def test_first_checkin_returns_immediate_feedback():
    r = checkin('first_day', 'morning', MORNING)
    assert r.status_code == 200
    body = r.json()
    assert body['saved'] == 3 and body['feedback_status'] == 'ready'
    fb = body['feedback']
    assert fb['schema_version'] == 'nexgene.progressive/1'
    assert {v['kind'] for v in fb['today']['values']} == set(MORNING)
    assert fb['levels']['observations']['status'] == 'available'
    assert fb['levels']['baseline']['status'] == 'locked'
    assert fb['highest_level'] == 1
    assert fb['today']['periods']['morning']['status'] == 'complete'
    assert fb['today']['periods']['evening']['status'] == 'missing'
    assert fb['generation']['language_model_used'] is False


def test_evening_checkin_with_the_ui_payload_is_accepted():
    # Regression: every evening payload the UI could produce used to be rejected with HTTP 422.
    r = checkin('evening_ui', 'evening', EVENING_UI)
    assert r.status_code == 200, r.text
    assert r.json()['saved'] == len(EVENING_UI)
    assert checkin('evening_ui', 'evening', {'caffeine': '2', 'alcohol': '3'}).status_code == 200   # older cached client


def test_new_checkin_is_visible_everywhere_without_a_reload():
    checkin('visible', 'morning', MORNING)
    client, _ = user('visible')
    prog = client.get('/api/v1/intelligence/progressive').json()
    assert {v['kind'] for v in prog['today']['values']} == set(MORNING)
    signals = client.get('/api/v1/signals').json()
    assert signals['status'] == 'active' and signals['signals'][0]['type'] == 'observation'
    insights = client.get('/api/v1/insights').json()
    assert insights['items'] and insights['status'] in ('baseline_forming', 'active')
    assert client.get('/api/v1/today').json()['energy'] == 8                      # legacy endpoint still works
    patterns = client.get('/api/v1/patterns').json()
    assert patterns['days_with_data'] == 1 and len(patterns['series']) == 1       # one sparse day is a valid series
    assert patterns['per_kind_days']['energy'] == 1
    timeline = client.get('/api/v1/timeline').json()
    assert {t['kind'] for t in timeline} == set(MORNING)


def test_insights_never_claim_a_relationship_from_one_reading():
    checkin('no_overclaim', 'morning', {'sleep_duration': 6, 'energy': 5})
    checkin('no_overclaim', 'evening', {'stress': 7})
    client, _ = user('no_overclaim')
    text = json.dumps(client.get('/api/v1/insights').json()).lower() + json.dumps(client.get('/api/v1/signals').json()).lower()
    assert 'relationships between' not in text and 'move together' not in text and 'thread between' not in text


def test_skipped_answers_are_not_stored():
    r = checkin('skipper', 'morning', {'energy': 7, 'morning_context': 'skipped'})
    assert r.status_code == 200 and r.json()['saved'] == 1
    client, _ = user('skipper')
    assert 'morning_context' not in {t['kind'] for t in client.get('/api/v1/timeline').json()}
    assert checkin('skipper', 'evening', {'activity_level': 'skipped'}).json()['saved'] == 0


def test_invalid_values_are_still_rejected():
    for bad in ({'energy': 'abc'}, {'energy': 99}, {'made_up_kind': 1}, {'activity_level': 'huge'}, {'morning_context': 'x' * 257}):
        assert checkin('first_day', 'morning', bad).status_code == 422, bad


def test_repeated_checkins_are_both_kept_and_flagged():
    checkin('repeater', 'morning', {'energy': 4})
    r = checkin('repeater', 'morning', {'energy': 8})
    assert r.status_code == 200
    energy = [v for v in r.json()['feedback']['today']['values'] if v['kind'] == 'energy'][0]
    assert energy['n_readings'] == 2 and energy['value'] == 8 and energy['day_mean'] == 6.0


def test_checkin_still_requires_a_session_and_csrf():
    anon = TestClient(app)
    assert anon.post('/api/v1/checkins/morning', json={'values': {'energy': 7}}).status_code in (401, 403)
    assert anon.get('/api/v1/intelligence/progressive').status_code == 401
    client, _ = user('first_day')
    assert client.post('/api/v1/checkins/morning', json={'values': {'energy': 7}}).status_code == 403   # no CSRF header


def test_user_level_isolation():
    checkin('iso_a', 'morning', {'energy': 9, 'morning_context': 'headache'})
    client_b, _ = user('iso_b')
    for path in ('/api/v1/intelligence/progressive', '/api/v1/signals', '/api/v1/insights', '/api/v1/patterns', '/api/v1/timeline', '/api/v1/reports/weekly', '/api/v1/today'):
        text = json.dumps(client_b.get(path).json()).lower()
        assert 'headache' not in text, path
    prog_b = client_b.get('/api/v1/intelligence/progressive').json()
    assert prog_b['today']['values'] == [] and prog_b['coverage']['total_observations'] == 0
    assert prog_b['signals']['status'] == 'starting'
    # and A's data really is there, so the assertions above are not vacuous
    client_a, _ = user('iso_a')
    assert 'headache' in json.dumps(client_a.get('/api/v1/timeline').json()).lower()


def test_weekly_report_is_useful_with_one_day_of_data():
    checkin('weekly_sparse', 'morning', MORNING)
    client, _ = user('weekly_sparse')
    r = client.get('/api/v1/reports/weekly')
    assert r.status_code == 200
    body = r.json()
    assert body['schema_version'] == 'nexgene.weekly_report/1'          # legacy contract unchanged
    ids = [s['id'] for s in body['layout']]
    assert ids == ['overview', 'recorded_observations', 'descriptive_insights', 'emerging_patterns', 'personal_baseline', 'coverage_limitations', 'next_observations']
    by = {s['id']: s for s in body['layout']}
    assert by['overview']['status'] == 'ready' and by['recorded_observations']['status'] == 'ready'
    assert by['coverage_limitations']['collapsed'] is True
    assert by['personal_baseline']['status'] == 'locked'


def test_empty_user_gets_a_welcome_and_a_layout():
    client, _ = user('brand_new')
    prog = client.get('/api/v1/intelligence/progressive').json()
    assert prog['highest_level'] == 0 and prog['signals']['status'] == 'starting'
    report = client.get('/api/v1/reports/weekly').json()
    assert report['status'] == 'not_ready' and report['layout'][0]['status'] == 'empty'


def test_consent_compartments_are_untouched_by_progressive_output():
    client, _ = user('first_day')
    text = json.dumps(client.get('/api/v1/intelligence/progressive').json()).lower()
    for compartment_term in ('polygenic', 'subject_ref', 'clinical_record', 'genomic_variant'):
        assert compartment_term not in text
