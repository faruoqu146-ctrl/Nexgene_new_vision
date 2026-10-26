"""Canonical temporal contract for NexGene observations.

Two different instants exist for every observation and they are NOT interchangeable:

  observed_at  when the measurement / event actually happened (event time)
  recorded_at  when NexGene received and stored the row (ingestion time)

Rules enforced here (and used by the weekly report):

  1. Historical analysis uses event time. ``event_time_of`` returns ``observed_at`` when it
     is present. Legacy rows written before ``observed_at`` existed fall back to
     ``recorded_at`` and are labelled ``recorded_at_legacy`` so callers can disclose that
     the event time is an assumption, never silently treat it as measured.
  2. Naive datetimes read back from SQLite are interpreted as UTC (the storage convention).
     Naive datetimes *submitted by a client* are rejected: they are ambiguous.
  3. Missing event times are quarantined, never reinterpreted as "now".
  4. Future-dated events (beyond a small clock-skew tolerance) are quarantined and counted.
  5. Reporting days are calendar days in the user's timezone, not rolling 24-hour blocks.
  6. Exact duplicates (same kind, same instant, same value) count once, so re-importing a
     batch cannot inflate observation counts or active days.

This module has no third-party dependencies so it can be unit-tested in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

FUTURE_TOLERANCE = timedelta(minutes=5)
MAX_BACKDATE = timedelta(days=3650)

BASIS_OBSERVED = "observed_at"
BASIS_LEGACY = "recorded_at_legacy"
BASIS_MISSING = "missing"


class EventTimeError(ValueError):
    """A client-supplied event time violates the temporal contract."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def as_utc(dt: datetime) -> datetime:
    """Normalise a stored datetime to aware UTC. Naive values are treated as UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_event_time(value: Optional[datetime], *, now: datetime) -> datetime:
    """Validate a client-supplied event time and return it as aware UTC.

    ``None`` means a live observation: the event time is the moment of ingestion.
    """
    now_utc = as_utc(now)
    if value is None:
        return now_utc
    if value.tzinfo is None:
        raise EventTimeError("naive_event_time", "observed_at must include a UTC offset")
    value_utc = value.astimezone(timezone.utc)
    if value_utc > now_utc + FUTURE_TOLERANCE:
        raise EventTimeError("future_event_time", "observed_at cannot be in the future")
    if value_utc < now_utc - MAX_BACKDATE:
        raise EventTimeError("event_time_too_old", "observed_at is too far in the past")
    return value_utc


def event_time_of(record) -> tuple[Optional[datetime], str]:
    """Return ``(event_utc, basis)`` for a stored observation-like row.

    basis is ``observed_at``, ``recorded_at_legacy``, or ``missing``.
    Never invents a timestamp.
    """
    observed = getattr(record, "observed_at", None)
    if observed is not None:
        return as_utc(observed), BASIS_OBSERVED
    recorded = getattr(record, "recorded_at", None)
    if recorded is not None:
        return as_utc(recorded), BASIS_LEGACY
    return None, BASIS_MISSING


def resolve_tz(name: Optional[str]):
    """Resolve an IANA timezone name. Returns ``(tzinfo, fell_back_to_utc)``."""
    if not name or not str(name).strip():
        return timezone.utc, True
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(str(name).strip()), False
    except Exception:
        return timezone.utc, True


def local_day(dt_utc: datetime, tz) -> date:
    """Calendar day of an aware UTC instant in the given timezone."""
    return as_utc(dt_utc).astimezone(tz).date()


@dataclass(frozen=True)
class ReportingWindow:
    tz_name: str
    tz_fallback: bool  # True when timezone fell back to UTC (weekly.py reads this name)
    week_start: date
    week_end: date
    baseline_start: date
    baseline_end: date

    @property
    def tz_fell_back(self) -> bool:
        """Alias for older callers."""
        return self.tz_fallback


def weekly_window(now: datetime, tz_name: Optional[str] = "UTC", *, week_days: int = 7, baseline_days: int = 21) -> ReportingWindow:
    tz, fell_back = resolve_tz(tz_name)
    today = local_day(now, tz)
    week_start = today - timedelta(days=week_days - 1)
    baseline_end = week_start - timedelta(days=1)
    baseline_start = baseline_end - timedelta(days=baseline_days - 1)
    return ReportingWindow(tz_name or "UTC", fell_back, week_start, today, baseline_start, baseline_end)


@dataclass(frozen=True)
class Obs:
    kind: str
    value_numeric: Optional[float]
    value_text: Optional[str]
    day: date
    event_utc: datetime
    basis: str


@dataclass
class Bucketed:
    week: list = field(default_factory=list)
    baseline: list = field(default_factory=list)
    outside_window: int = 0
    missing_event_time: int = 0
    future_dated: int = 0
    duplicates_dropped: int = 0
    legacy_event_time: int = 0

    @property
    def quarantined(self) -> dict:
        return {"missing_event_time": self.missing_event_time, "future_dated": self.future_dated}


def bucket_observations(records: Iterable, window: ReportingWindow, now: datetime) -> Bucketed:
    """Assign rows to week / baseline by EVENT day. Deterministic and import-order independent."""
    tz, _ = resolve_tz(window.tz_name)
    now_utc = as_utc(now)
    out = Bucketed()
    seen = set()
    items = []
    for rec in records:
        event, basis = event_time_of(rec)
        if event is None:
            out.missing_event_time += 1
            continue
        if event > now_utc + FUTURE_TOLERANCE:
            out.future_dated += 1
            continue
        num = getattr(rec, "value_numeric", None)
        txt = getattr(rec, "value_text", None)
        key = (str(rec.kind), event, num, txt)
        if key in seen:
            out.duplicates_dropped += 1
            continue
        seen.add(key)
        items.append(Obs(str(rec.kind), None if num is None else float(num), txt, local_day(event, tz), event, basis))
    items.sort(key=lambda o: (o.event_utc, o.kind, o.value_numeric if o.value_numeric is not None else float("-inf"), o.value_text or ""))
    for o in items:
        if window.week_start <= o.day <= window.week_end:
            out.week.append(o)
        elif window.baseline_start <= o.day <= window.baseline_end:
            out.baseline.append(o)
        else:
            out.outside_window += 1
            continue
        if o.basis == BASIS_LEGACY:
            out.legacy_event_time += 1
    return out
