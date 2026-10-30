"""Discovery pipeline (boot-safe stub — replace with full surface module)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

LIMITATIONS = [
    "Self-reported data is noisy and incomplete.",
    "Associations are not causal claims.",
]


@dataclass
class ResearchResult:
    candidates: list = field(default_factory=list)
    limitations: list = field(default_factory=lambda: list(LIMITATIONS))
    meta: dict = field(default_factory=dict)


def analyze_panel(panel, config=None, **kwargs) -> ResearchResult:
    """Return an empty, honest result until the full engine module is installed."""
    return ResearchResult(meta={"status": "stub", "note": "Full discovery module not installed"})
