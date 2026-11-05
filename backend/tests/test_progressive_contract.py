"""Static contract tests for the progressive-intelligence wiring (read source text; no web stack needed)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / 'backend/app/main.py').read_text()
PROGRESSIVE = (ROOT / 'backend/app/progressive.py').read_text()
CHECKIN = (ROOT / 'backend/app/checkin.py').read_text()


def _function_source(name):
    m = re.search(rf'^def {name}\(.*?(?=^(?:def |@app\.|class )|\Z)', MAIN, re.S | re.M)
    assert m, name
    return m.group(0)


def test_checkin_persists_before_building_feedback_and_feedback_cannot_fail_the_save():
    src = _function_source('save_checkin')
    assert src.index('s.commit()') < src.index('_build_progressive_for(u, s)')
    assert 'feedback_status' in src and 'except Exception' in src and 'unavailable' in src
    assert 'ObservationSourceLink(' in src           # provenance link is still written for every observation


def test_new_endpoint_and_report_use_the_progressive_module():
    assert '/api/v1/intelligence/progressive' in MAIN
    assert 'nre_progressive.build_weekly_report' in MAIN
    assert 'nre_progressive.build_progressive' in MAIN
    assert 'nre_weekly.build_weekly_report(' not in MAIN     # the report is assembled through progressive (which wraps it)


def test_every_new_query_is_scoped_to_the_authenticated_user():
    for name in ('_engine_inputs', '_build_progressive_for', 'weekly_report', 'patterns'):
        src = _function_source(name)
        assert 'select(' in src, name
        for m in re.finditer(r'select\((?:Observation|IntelligenceRun|Hypothesis|Profile)[^)]*\)[^\n]*', src):
            assert 'user_id == u.id' in src[m.start():m.start() + 400], (name, m.group(0)[:80])


def test_progressive_module_is_pure_and_cannot_reach_consent_compartments():
    for forbidden in ('sqlalchemy', 'ClinicalRecord', 'GenomicVariant', 'PolygenicScore', 'subject_ref', 'requests', 'httpx', 'openai', 'import os'):
        assert forbidden not in PROGRESSIVE, forbidden
    assert 'language_model_used": False' in PROGRESSIVE


def test_validator_delegates_to_the_shared_rules_and_keeps_the_old_names_importable():
    assert 'normalize_values(' in MAIN and 'CheckinValueError' in MAIN
    assert 'NUMERIC_OBSERVATION_RANGES' in MAIN and 'ALLOWED_OBSERVATIONS' in MAIN
    assert 'import ' not in CHECKIN.replace('from __future__ import annotations', '').replace('import math', '').replace('from typing import Mapping', '')


def test_app_version_and_existing_contract_strings_are_unchanged():
    assert 'APP_VERSION = "1.9.0"' in MAIN
    assert '/api/v1/reports/weekly' in MAIN and '/api/v1/signals' in MAIN and '/api/v1/insights' in MAIN and '/api/v1/patterns' in MAIN
