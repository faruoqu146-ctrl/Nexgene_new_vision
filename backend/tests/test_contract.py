from pathlib import Path


def test_v130_contract():
    root = Path(__file__).parents[2]
    main = (root / 'backend/app/main.py').read_text()
    js = (root / 'mobile/app.js').read_text()
    html = (root / 'mobile/index.html').read_text()
    compose = (root / 'docker-compose.yml').read_text()
    readme = (root / 'README.md').read_text()
    assert 'APP_VERSION = "1.9.0"' in main
    assert 'FileResponse("mobile/index.html")' in main
    assert 'app.mount("/static"' in main
    assert 'window.location.origin' in js
    assert '/api/v1/auth/login' in js and '/api/v1/auth/register' in js
    assert '/api/v1/auth/me' in js
    assert '/api/v1/patterns' in main and '/api/v1/insights' in main and '/api/v1/signals' in main and '/api/v1/profile' in main and '/api/v1/reports/weekly' in main and '/api/v1/biomarkers/signals' in main and '/api/v1/intelligence/brief' in main and '/api/v1/evidence/search' in main and '/api/v1/intelligence/insights' in main and '/api/v1/intelligence/data-quality' in main
    assert '/static/styles.css' in html and '/static/app.js' in html
    assert 'nexgene_data' in compose
    assert 'activity_level' in js and 'diet_quality' in js and 'nicotine' in js
    assert 'innerHTML' not in js
    assert 'DUMMY_PASSWORD_HASH' in main
    assert 'RateLimitBucket' in main
    assert 'docs_url="/docs" if DEV_MODE else None' in main
    assert 'APP_VERSION' in readme and 'v1.9.0' in readme and 'Phase 12' in readme and 'missingness diagnostics' in readme
