"""Purpose-specific consent helpers.

Consent is purpose-scoped. A user may allow collection and personal insights
without allowing research reuse or cross-domain combination.
"""
from __future__ import annotations

from typing import Iterable, Optional, Set

# Stable purpose identifiers (versioned policy can map these later).
PURPOSE_COLLECT = "collect"
PURPOSE_PERSONAL_INSIGHT = "personal_insight"
PURPOSE_CROSS_DOMAIN = "cross_domain"
PURPOSE_PREDICTION = "prediction"
PURPOSE_RESEARCH = "research"
PURPOSE_EXPORT = "export"

ALL_PURPOSES = frozenset({
    PURPOSE_COLLECT,
    PURPOSE_PERSONAL_INSIGHT,
    PURPOSE_CROSS_DOMAIN,
    PURPOSE_PREDICTION,
    PURPOSE_RESEARCH,
    PURPOSE_EXPORT,
})

# Default purposes granted when a user starts logging lifestyle data.
DEFAULT_LIFESTYLE_PURPOSES = frozenset({
    PURPOSE_COLLECT,
    PURPOSE_PERSONAL_INSIGHT,
})


def normalize_purposes(purposes: Optional[Iterable[str]]) -> Set[str]:
    if not purposes:
        return set()
    out = set()
    for p in purposes:
        if not p:
            continue
        key = str(p).strip().lower()
        if key in ALL_PURPOSES:
            out.add(key)
    return out


def consent_allows(granted: Optional[Iterable[str]], required: str) -> bool:
    """Return True if the required purpose is present in the granted set."""
    if required not in ALL_PURPOSES:
        return False
    return required in normalize_purposes(granted)


def missing_purposes(granted: Optional[Iterable[str]], required: Iterable[str]) -> Set[str]:
    g = normalize_purposes(granted)
    return {r for r in required if r in ALL_PURPOSES and r not in g}
