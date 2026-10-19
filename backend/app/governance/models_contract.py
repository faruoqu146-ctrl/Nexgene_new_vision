"""Contracts for consent records and canonical observation enrichment.

These are schema contracts, not SQLAlchemy models. The application layer maps
them into tables when migrations are applied. Keeping contracts separate lets
tests and documentation stay stable while the monolith is restored.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ConsentRecordContract:
    subject_id: int
    purpose: str
    data_category: str  # e.g. lifestyle, clinical, genomic
    granted: bool
    policy_version: str
    granted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    recipient: Optional[str] = None  # processor / research cohort if any


@dataclass
class CanonicalObservationContract:
    """Minimal fields required by the NexGene master observation model."""
    observation_id: Optional[int]
    subject_id: int
    data_domain: str  # lifestyle | physiological | clinical | biomarker | genomic | environmental
    observation_type: str  # maps from kind
    source_type: str  # user-entered | imported | measured | derived | model-generated
    value: Any
    value_type: str  # numeric | categorical | text
    unit: Optional[str] = None
    observed_at: Optional[datetime] = None  # event time
    recorded_at: Optional[datetime] = None  # ingestion time
    source_id: Optional[int] = None
    quality_flag: str = "unknown"
    consent_purposes: List[str] = field(default_factory=list)
    sensitivity: str = "personal_health"
    metadata: Dict[str, Any] = field(default_factory=dict)


def observation_from_checkin(
    *,
    subject_id: int,
    kind: str,
    value: Any,
    recorded_at: datetime,
    source_id: Optional[int] = None,
    period: str = "morning",
) -> CanonicalObservationContract:
    value_type = "numeric" if isinstance(value, (int, float)) else "text"
    return CanonicalObservationContract(
        observation_id=None,
        subject_id=subject_id,
        data_domain="lifestyle",
        observation_type=kind,
        source_type="user-entered",
        value=value,
        value_type=value_type,
        unit=None,
        observed_at=recorded_at,
        recorded_at=recorded_at,
        source_id=source_id,
        quality_flag="self_reported",
        consent_purposes=["collect", "personal_insight"],
        sensitivity="personal_health",
        metadata={"period": period},
    )
