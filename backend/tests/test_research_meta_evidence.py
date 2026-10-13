import json
import math
import tempfile
from pathlib import Path

import numpy as np

from _research_helpers import ROOT  # noqa: F401
from backend.app.research.evidence import build_queries, load_priors, rank_sources, terms_for
from backend.app.research.meta import MIN_PEOPLE, population_prior, random_effects


def test_pooling_refuses_small_groups_so_nobody_is_identifiable():
    assert random_effects([0.3] * (MIN_PEOPLE - 1), [0.1] * (MIN_PEOPLE - 1))["pooled"] is False
    assert population_prior([0.3] * 3, [0.1] * 3)["available"] is False


def test_random_effects_recovers_a_homogeneous_effect():
    rng = np.random.default_rng(1)
    se = np.full(40, 0.1)
    est = 0.3 + rng.normal(0, 0.1, 40)
    r = random_effects(est, se)
    assert r["pooled"] and abs(r["mean"] - 0.3) < 0.06 and r["i2"] < 0.35 and r["ci95"][0] < 0.3 < r["ci95"][1]
    assert r["prediction_interval95"][0] <= r["ci95"][0] and r["prediction_interval95"][1] >= r["ci95"][1]


def test_random_effects_detects_heterogeneity():
    rng = np.random.default_rng(2)
    est = rng.normal(0.3, 0.3, 40)
    r = random_effects(est, np.full(40, 0.05))
    assert r["i2"] > 0.8 and r["tau"] > 0.2
    p = population_prior(est, np.full(40, 0.05))
    assert p["available"] and p["sd"] >= 0.05 and p["k"] == 40


def test_random_effects_validates_inputs():
    for bad in (lambda: random_effects([0.1] * 12, [0.1] * 11), lambda: random_effects([0.1] * 12, [0.0] * 12)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("invalid input accepted")


SOURCES = [
    {"id": 1, "title": "Caffeine intake and sleep quality in adults", "abstract_summary": "", "topic_tags": ["sleep"], "evidence_grade": "B", "published_year": 2020, "url": "u1"},
    {"id": 2, "title": "Caffeine pharmacokinetics", "abstract_summary": "No sleep outcomes.", "topic_tags": [], "evidence_grade": "C", "published_year": 2018, "url": "u2"},
    {"id": 3, "title": "Exercise and mood", "abstract_summary": "", "topic_tags": ["mood"], "evidence_grade": "B", "published_year": 2021, "url": "u3"},
]


def test_retrieved_literature_must_mention_both_sides_and_is_never_called_support():
    hits = rank_sources(SOURCES, "caffeine", "sleep_quality")
    ids = [h["id"] for h in hits]
    assert 1 in ids and 3 not in ids
    assert all(h["appraised"] is False and "not evidence" in h["note"].lower() for h in hits)
    assert rank_sources(SOURCES, "alcohol", "focus") == []


def test_search_queries_are_generated_from_synonyms():
    qs = build_queries("caffeine", "sleep_quality")
    assert qs and all(" AND " in q for q in qs) and '"caffeine"' in qs[0]
    assert "heart rate variability" in terms_for("hrv") and terms_for("bm:crp") == ["crp"]


def test_only_reviewed_and_cited_priors_are_loaded():
    data = {"priors": [
        {"exposure": "caffeine", "outcome": "sleep_quality", "expected_sign": -1, "review_status": "reviewed", "citations": ["doi:10.0/x"], "reviewer": "dr"},
        {"exposure": "alcohol", "outcome": "mood", "expected_sign": -1, "review_status": "unreviewed", "citations": ["doi:y"]},
        {"exposure": "stress", "outcome": "focus", "expected_sign": -1, "review_status": "reviewed", "citations": []},
        {"exposure": "x", "outcome": "y", "expected_sign": 0, "review_status": "reviewed", "citations": ["z"]},
    ]}
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "priors.json"
        path.write_text(json.dumps(data))
        pri = load_priors(str(path))
    assert list(pri) == [("caffeine", "sleep_quality")] and pri[("caffeine", "sleep_quality")]["expected_sign"] == -1
    assert load_priors(None) == {} and load_priors("/nonexistent/priors.json") == {}
