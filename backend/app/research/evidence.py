"""Literature linking and reviewed priors.

Retrieved literature is *context*, not support: a paper that mentions both variables does
not make a hypothesis more likely, and nothing here changes a p-value or an evidence tier.
Only entries a human has marked ``reviewed`` (with citations) in a priors file can act,
and then only as a concordance gate on the direction of an association.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .config import LABELS

SYNONYMS = {
    "sleep_duration": ["sleep duration", "sleep length", "time asleep"],
    "sleep_quality": ["sleep quality"],
    "energy": ["energy", "fatigue"],
    "mood": ["mood", "affect"],
    "stress": ["stress", "perceived stress"],
    "focus": ["attention", "concentration", "focus"],
    "activity_level": ["physical activity"],
    "activity_duration": ["exercise duration", "physical activity"],
    "diet_quality": ["diet quality", "dietary pattern"],
    "caffeine": ["caffeine", "coffee"],
    "alcohol": ["alcohol"],
    "nicotine": ["nicotine", "smoking"],
    "weight": ["body weight"],
    "heart_rate": ["heart rate", "resting heart rate"],
    "hrv": ["heart rate variability", "HRV"],
    "blood_pressure_systolic": ["systolic blood pressure"],
    "blood_pressure_diastolic": ["diastolic blood pressure"],
    "glucose": ["blood glucose", "glycaemia"],
    "temperature": ["body temperature"],
}
_TOKEN = re.compile(r"[a-z0-9]{3,}")


def terms_for(kind: str) -> list:
    if kind in SYNONYMS:
        return SYNONYMS[kind]
    if kind.startswith("bm:"):
        return [kind[3:].replace("_", " ")]
    return [LABELS.get(kind, (kind.replace("_", " "), ""))[0]]


def build_queries(exposure: str, outcome: str, limit: int = 3) -> list:
    """Search strings a person (or the live-search endpoint) can run; the engine never treats results as support."""
    qs = []
    for xt in terms_for(exposure)[:2]:
        for yt in terms_for(outcome)[:2]:
            qs.append(f'"{xt}" AND "{yt}"')
    return qs[:limit]


def _tokens(text: str) -> set:
    return set(_TOKEN.findall((text or "").lower()))


def rank_sources(sources: list, exposure: str, outcome: str, limit: int = 5) -> list:
    """Rank stored evidence sources by whether they mention BOTH sides of the relationship.

    ``sources``: dicts with id, title, abstract_summary, topic_tags, evidence_grade, published_year, url.
    """
    xt = {t for term in terms_for(exposure) for t in _tokens(term)}
    yt = {t for term in terms_for(outcome) for t in _tokens(term)}
    out = []
    for s in sources:
        corpus = _tokens((s.get("title") or "") + " " + (s.get("abstract_summary") or "")) | _tokens(" ".join(map(str, s.get("topic_tags") or [])))
        hx, hy = len(xt & corpus), len(yt & corpus)
        if hx and hy:
            out.append({"id": s.get("id"), "title": s.get("title"), "published_year": s.get("published_year"),
                        "evidence_grade": s.get("evidence_grade"), "url": s.get("url"), "relevance": hx + hy,
                        "appraised": False, "note": "Retrieved for context; not evidence for or against this hypothesis."})
    out.sort(key=lambda r: (-r["relevance"], -(r["published_year"] or 0)))
    return out[:limit]


def load_priors(path: Optional[str]) -> dict:
    """Load reviewed directional priors: {(exposure, outcome): {...}}. Unreviewed or uncited entries are dropped."""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text())
    out = {}
    for item in raw.get("priors", []):
        if item.get("review_status") != "reviewed" or not item.get("citations"):
            continue
        if item.get("expected_sign") not in (-1, 1):
            continue
        out[(item["exposure"], item["outcome"])] = {
            "expected_sign": int(item["expected_sign"]), "review_status": "reviewed",
            "citations": list(item["citations"]), "reviewer": item.get("reviewer"),
        }
    return out
