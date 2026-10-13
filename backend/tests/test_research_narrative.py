import copy
import re

from _research_helpers import planted_panel
from backend.app.research import analyze_panel, build_brief, describe_candidate, next_experiments
from backend.app.research.narrative import alternatives_for, prediction_text, rationale_for

FORBIDDEN = re.compile(r"\b(cause[sd]?|causing|treat(s|ed|ment)?|cure[sd]?|diagnos\w*|prescrib\w*|you should|must)\b", re.I)
RES = analyze_panel(planted_panel(seed=7))


def _cand(level):
    c = copy.deepcopy(next(c for c in RES.candidates if c["id"] == "activity_duration->mood@1"))
    c["tier"] = {**c["tier"], "level": level, "code": f"ERL-{level}", "label": "x"}
    return c


def test_language_is_a_function_of_the_tier_and_never_claims_causation_or_treatment():
    for level in range(6):
        d = describe_candidate(_cand(level))
        for field in ("headline", "effect", "evidence"):
            assert not FORBIDDEN.search(d[field]), (level, field, d[field])
    assert "associated" in describe_candidate(_cand(2))["headline"]
    assert "followed by" in describe_candidate(_cand(3))["headline"]
    assert "locked model" in describe_candidate(_cand(4))["headline"]
    assert "randomised self-experiment" in describe_candidate(_cand(5))["headline"]
    assert "unconfirmed" in describe_candidate(_cand(1))["headline"]


def test_every_finding_carries_caveats_and_falsifiers():
    for c in RES.candidates[:10]:
        if c["tier"]["level"] >= 1:
            d = describe_candidate(c)
            assert d["caveats"] and "does not show that one thing causes" in d["caveats"][0] and d["falsifiers"]


def test_effect_sentence_uses_natural_units():
    d = describe_candidate(_cand(3))
    assert "mood" in d["effect"] and "activity duration" in d["effect"] and "next day" in d["effect"] and "adjusted r" in d["effect"]


def test_falsified_and_weakened_statuses_change_the_headline():
    c = _cand(3)
    c["status"] = "FALSIFIED"
    assert "did not support" in describe_candidate(c)["headline"]
    c["status"] = "WEAKENED"
    assert "weakening" in describe_candidate(c)["headline"]


def test_helper_texts_are_hypothesis_specific_and_non_empty():
    c = _cand(3)
    assert "next day" in prediction_text(c) and "higher" in prediction_text(c)
    assert alternatives_for(c) and "reverse direction" in alternatives_for(c)[0]
    assert "temporal order" in rationale_for(c).lower()
    same_day = _cand(2)
    same_day["lag"] = 0
    assert "same-day" in alternatives_for(same_day)[0].lower() or "same day" in alternatives_for(same_day)[0].lower()


def test_brief_structure_and_escalation_flag():
    b = build_brief(RES)
    assert b["status"] == "active" and b["clinical_escalation"] == "not_assessed" and b["findings"]
    assert set(b["tier_counts"]) == {f"ERL-{i}" for i in range(6)} and sum(b["tier_counts"].values()) == len(RES.candidates)
    assert any("not diagnoses" in s for s in b["limitations"])
    assert b["data_quality"]["score"] > 0


def test_next_experiments_only_suggests_assignable_exposures_with_real_signal():
    for e in next_experiments(RES, limit=10):
        assert e["exposure"] in {"caffeine", "alcohol", "nicotine", "activity_level", "activity_duration", "diet_quality", "sleep_duration"}
        c = next(c for c in RES.candidates if c["id"] == e["candidate_id"])
        assert c["tier"]["level"] >= 2 and e["feasible_in_8_weeks"] in (True, False)
