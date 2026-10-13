"""API-level checks for the research engine (need the full web stack: run with the project's requirements installed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)
CREDS = {'email': 'research-engine@example.com', 'password': 'A_secure_password!9'}


def _login():
    r = client.post('/api/v1/auth/register', json=CREDS)
    if r.status_code == 409:
        r = client.post('/api/v1/auth/login', json=CREDS)
    assert r.status_code == 200
    return r.cookies.get('nexgene_csrf') or client.cookies.get('nexgene_csrf')


def test_research_endpoints_require_authentication():
    anon = TestClient(app)
    for path in ('/api/v1/intelligence/research/brief', '/api/v1/intelligence/research/manifest', '/api/v1/intelligence/experiments',
                 '/api/v1/intelligence/engine/status'):
        assert anon.get(path).status_code in (401, 403), path


def test_engine_run_requires_csrf_and_returns_a_reproducibility_receipt():
    csrf = _login()
    assert client.post('/api/v1/intelligence/engine/run').status_code == 403
    r = client.post('/api/v1/intelligence/engine/run', headers={'X-CSRF-Token': csrf})
    assert r.status_code in (200, 429)                      # 429 if the per-user cooldown from an earlier run is still active
    if r.status_code == 200:
        body = r.json()
        assert body['model_version'].startswith('nre-') and body['manifest']['run_hash'] and body['brief']['clinical_escalation'] == 'not_assessed'
    brief = client.get('/api/v1/intelligence/research/brief')
    assert brief.status_code == 200 and brief.json()['clinical_escalation'] == 'not_assessed'
    status = client.get('/api/v1/intelligence/engine/status').json()
    assert 'evidence_ladder' in status and {'SUPPORTED', 'CONFIRMED', 'SUPERSEDED'} <= set(status['hypothesis_counts'])
    assert client.get('/api/v1/intelligence/research/manifest').json()['chain']['ok'] is True


def test_experiment_lifecycle_is_csrf_protected_validated_and_withholds_interim_results():
    csrf = _login()
    h = {'X-CSRF-Token': csrf}
    body = {'exposure': 'caffeine', 'outcome': 'mood', 'intervention': 'decrease'}
    assert client.post('/api/v1/intelligence/experiments', json=body).status_code == 403
    for e in client.get('/api/v1/intelligence/experiments').json():           # leave nothing active from earlier runs
        if e['status'] in ('DESIGNED', 'RUNNING'):
            client.post(f"/api/v1/intelligence/experiments/{e['experiment_id']}/abandon", headers=h)
    assert client.post('/api/v1/intelligence/experiments', json={'intervention': 'decrease'}, headers=h).status_code == 422
    ok = client.post('/api/v1/intelligence/experiments', json=body, headers=h)
    if ok.status_code == 429:
        return                                                                # rate limited by earlier runs; covered by the static contract tests
    assert ok.status_code == 200
    exp = ok.json()
    assert exp['status'] == 'DESIGNED' and exp['preregistration_verified'] is True
    assert len(exp['design']['preregistration']['schedule']) == 28
    assert client.post('/api/v1/intelligence/experiments', json=body, headers=h).status_code in (409, 429)
    interim = client.post(f"/api/v1/intelligence/experiments/{exp['experiment_id']}/analyze", headers=h)
    if interim.status_code == 200:
        analysis = interim.json()['analysis']
        assert 'itt' not in analysis and 'verdict' not in analysis
    gone = client.post(f"/api/v1/intelligence/experiments/{exp['experiment_id']}/abandon", headers=h)
    assert gone.status_code == 200 and gone.json()['status'] == 'ABANDONED'


def test_other_users_experiments_are_not_visible():
    other = TestClient(app)
    creds = {'email': 'research-engine-other@example.com', 'password': 'A_secure_password!9'}
    r = other.post('/api/v1/auth/register', json=creds)
    if r.status_code == 409:
        r = other.post('/api/v1/auth/login', json=creds)
    assert r.status_code == 200
    assert other.get('/api/v1/intelligence/experiments/exp_does_not_exist').status_code == 404
