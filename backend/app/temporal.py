"""Canonical temporal contract for NexGene observations.

Two different instants exist for every observation and they are NOT interchangeable:

  observed_at  when the measurement / event actually happened (event time)
  recorded_at  when NexGene stored the row (ingestion time)

Historical analysis, weekly windows, baselines, patterns, and active-day counts MUST
use event time. recorded_at is retained for audit/provenance only.

Legacy rows may have observed_at IS NULL; for those we fall back to recorded_at and
tag the basis so callers can see the uncertainty. We never invent timestamps.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


class EventTimeError(ValueError):
    """Raised when an event timestamp is missing, naive, future, or otherwise invalid."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise EventTimeError("naive_datetime", "Event timestamps must include a UTC offset")
    return dt.astimezone(timezone.utc)


def validate_event_time(
    observed_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    max_future_skew: timedelta = timedelta(minutes=5),
) -> datetime:
    """Normalize and validate an optional client-supplied event time.

    - None => use now (live check-in)
    - Must be timezone-aware
    - Must not be more than max_future_skew ahead of now
    """
    clock = now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        clock = clock.replace(tzinfo=timezone.utc)
    else:
        clock = clock.astimezone(timezone.utc)

    if observed_at is None:
        return clock

    event = _aware_utc(observed_at)
    if event > clock + max_future_skew:
        raise EventTimeError("future_event_time", "observed_at cannot be in the future")
    return event


def event_time_of(row) -> Tuple[datetime, str]:
    """Return (aware_utc_event_time, basis) for an observation-like row.

    basis is 'observed_at' when the event field is set, else 'recorded_at_fallback'.
    """
    raw = getattr(row, "observed_at", None)
    if raw is not None:
        if getattr(raw, "tzinfo", None) is None:
            raw = raw.replace(tzinfo=timezone.utc)
        else:
            raw = raw.astimezone(timezone.utc)
        return raw, "observed_at"

    raw = getattr(row, "recorded_at", None)
    if raw is None:
        raise EventTimeError("missing_timestamps", "observation lacks observed_at and recorded_at")
    if getattr(raw, "tzinfo", None) is None:
        raw = raw.replace(tzinfo=timezone.utc)
    else:
        raw = raw.astimezone(timezone.utc)
    return raw, "recorded_at_fallback"


def weekly_window(now: Optional[datetime] = None, week_days: int = 7, baseline_days: int = 28):
    """Return (week_start, baseline_start, end) as aware UTC datetimes."""
    end = now or datetime.now(timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    else:
        end = end.astimezone(timezone.utc)
    week_start = end - timedelta(days=week_days)
    baseline_start = end - timedelta(days=baseline_days)
    return week_start, baseline_start, end
