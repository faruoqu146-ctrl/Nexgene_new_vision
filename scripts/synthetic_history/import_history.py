#!/usr/bin/env python3
"""Import synthetic historical check-ins into an isolated test account.

Safety:
  - Requires DEV_MODE=true or ALLOW_SYNTHETIC_IMPORT=true
  - Refuses production-looking hosts unless ALLOW_SYNTHETIC_IMPORT=true
  - Dedicated synthetic account only
  - --dry-run validates without writing
  - Idempotent on (user_id, kind, observed_at, period) for this dataset source

Usage:
  python scripts/synthetic_history/import_history.py --dry-run
  python scripts/synthetic_history/import_history.py --apply
  python scripts/synthetic_history/import_history.py --apply --limit-days 3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from passlib.context import CryptContext
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
    and_,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "dataset_v1.json"

SYN_EMAIL = os.getenv("SYNTHETIC_IMPORT_EMAIL", "synthetic.student@nexgene.test")
SYN_PASSWORD = os.getenv("SYNTHETIC_IMPORT_PASSWORD", "SyntheticStudent1!")
BATCH_SIZE = 16  # must match API MAX_CHECKIN_KEYS

pwd = CryptContext(schemes=["pbkdf2_sha256"], pbkdf2_sha256__default_rounds=600000, deprecated="auto")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    email_verified: Mapped[bool] = mapped_column(Boolean, default=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ai_analysis_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Profile(Base):
    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    age_range: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    student: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    study_field: Mapped[str | None] = mapped_column(String(120), nullable=True)
    schedule: Mapped[str | None] = mapped_column(String(80), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(160), nullable=True)
    live_context_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    data_category: Mapped[str] = mapped_column(String(40), index=True, default="lifestyle")
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    policy_version: Mapped[str] = mapped_column(String(32), default="v1")
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SourceRecord(Base):
    __tablename__ = "source_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active")
    reliability: Mapped[str] = mapped_column(String(32), default="unknown")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80), index=True)
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data_domain: Mapped[str] = mapped_column(String(40), default="lifestyle")
    source_type: Mapped[str] = mapped_column(String(40), default="user-entered")
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quality_flag: Mapped[str] = mapped_column(String(32), default="self_reported")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period: Mapped[str | None] = mapped_column(String(24), nullable=True)
    supersedes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ObservationSourceLink(Base):
    __tablename__ = "observation_source_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="origin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _env_allows_import() -> tuple[bool, str]:
    dev = os.getenv("DEV_MODE", "false").lower() == "true"
    allow = os.getenv("ALLOW_SYNTHETIC_IMPORT", "false").lower() == "true"
    if dev or allow:
        return True, "allowed"
    return False, "Refused: set DEV_MODE=true or ALLOW_SYNTHETIC_IMPORT=true"


def _parse_ts(value: str) -> datetime:
    v = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(v)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def load_dataset(path: Path) -> dict:
    data = json.loads(path.read_text())
    if not data.get("synthetic"):
        raise SystemExit("Dataset missing synthetic=true — refusing to import")
    if not data.get("dataset_id") or not data.get("dataset_version"):
        raise SystemExit("Dataset missing dataset_id/version")
    return data


def validate_records(records: list[dict]) -> list[str]:
    errors: list[str] = []
    allowed = {
        "sleep_duration", "sleep_quality", "energy", "morning_context",
        "mood", "stress", "focus", "activity_level", "diet_quality",
        "caffeine", "alcohol", "nicotine",
    }
    ranges = {
        "sleep_duration": (0.0, 24.0), "sleep_quality": (0.0, 10.0), "energy": (0.0, 10.0),
        "mood": (0.0, 10.0), "stress": (0.0, 10.0), "focus": (0.0, 10.0),
        "activity_level": (0.0, 10.0), "diet_quality": (0.0, 10.0),
        "caffeine": (0.0, 20.0), "alcohol": (0.0, 20.0), "nicotine": (0.0, 100.0),
    }
    for i, r in enumerate(records):
        kind = r.get("kind")
        if kind not in allowed:
            errors.append(f"row {i}: unsupported kind {kind}")
            continue
        val = r.get("value")
        if kind == "morning_context":
            if not isinstance(val, str) or len(val) > 256:
                errors.append(f"row {i}: invalid morning_context")
        else:
            try:
                num = float(val)
            except (TypeError, ValueError):
                errors.append(f"row {i}: non-numeric value for {kind}")
                continue
            lo, hi = ranges[kind]
            if num < lo or num > hi:
                errors.append(f"row {i}: {kind}={num} out of range [{lo},{hi}]")
        try:
            _parse_ts(r["observed_at"])
        except Exception:
            errors.append(f"row {i}: bad observed_at")
        if r.get("period") not in ("morning", "evening"):
            errors.append(f"row {i}: period must be morning|evening")
    return errors


def ensure_user(s: Session, profile: dict, email: str = SYN_EMAIL) -> User:
    now = datetime.now(timezone.utc)
    user = s.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=pwd.hash(SYN_PASSWORD),
            created_at=now,
            email_verified=True,
            ai_analysis_enabled=False,
        )
        s.add(user)
        s.flush()
        s.add(
            Profile(
                user_id=user.id,
                age_range=profile.get("age_range"),
                country=profile.get("country"),
                occupation=profile.get("occupation"),
                student=profile.get("student"),
                study_field=profile.get("study_field"),
                schedule="student",
                timezone=profile.get("timezone") or "Africa/Lagos",
                location_city=None,
                live_context_enabled=True,
                updated_at=now,
            )
        )
    # lifestyle collect + personal_insight consent
    for purpose in ("collect", "personal_insight"):
        existing = s.scalar(
            select(ConsentRecord).where(
                ConsentRecord.user_id == user.id,
                ConsentRecord.purpose == purpose,
                ConsentRecord.data_category == "lifestyle",
            )
        )
        if existing is None:
            s.add(
                ConsentRecord(
                    user_id=user.id,
                    purpose=purpose,
                    data_category="lifestyle",
                    granted=True,
                    policy_version="v1",
                    granted_at=now,
                )
            )
        elif not existing.granted:
            existing.granted = True
            existing.granted_at = now
            existing.revoked_at = None
    s.flush()
    return user


def ensure_source(s: Session, user: User, dataset: dict, import_batch_id: str) -> SourceRecord:
    label = f"SYNTHETIC {dataset['dataset_id']}@{dataset['dataset_version']}"
    meta = {
        "synthetic": True,
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "generator_version": dataset.get("generator_version"),
        "content_hash": dataset.get("content_hash"),
        "random_seed": dataset.get("random_seed"),
        "scenario_id": dataset.get("scenario_id"),
        "subject_id": dataset.get("subject_id"),
        "import_batch_id": import_batch_id,
        "label_warning": "SYNTHETIC DATA — not real participant observations",
    }
    source = s.scalar(
        select(SourceRecord).where(
            SourceRecord.user_id == user.id,
            SourceRecord.label == label,
            SourceRecord.status == "active",
        )
    )
    now = datetime.now(timezone.utc)
    if source is None:
        source = SourceRecord(
            user_id=user.id,
            source_type="synthetic_import",
            label=label[:200],
            status="active",
            reliability="synthetic",
            metadata_json=json.dumps(meta),
            created_at=now,
        )
        s.add(source)
        s.flush()
    else:
        # merge batch id into metadata
        try:
            prev = json.loads(source.metadata_json or "{}")
        except Exception:
            prev = {}
        prev.update(meta)
        source.metadata_json = json.dumps(prev)
        s.flush()
    return source


def already_imported(s: Session, user_id: int, kind: str, observed_at: datetime, period: str | None) -> bool:
    q = select(Observation.id).where(
        Observation.user_id == user_id,
        Observation.kind == kind,
        Observation.observed_at == observed_at,
    )
    if period is not None:
        q = q.where(Observation.period == period)
    return s.scalar(q.limit(1)) is not None


def import_records(
    s: Session,
    user: User,
    source: SourceRecord,
    records: list[dict],
    *,
    dry_run: bool,
) -> dict:
    recorded = datetime.now(timezone.utc)
    accepted = 0
    skipped = 0
    rejected = 0
    for r in records:
        kind = r["kind"]
        observed = _parse_ts(r["observed_at"])
        period = r.get("period")
        if already_imported(s, user.id, kind, observed, period):
            skipped += 1
            continue
        val = r["value"]
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            value_numeric = float(val)
            value_text = None
        else:
            value_numeric = None
            value_text = str(val)
        if dry_run:
            accepted += 1
            continue
        obs = Observation(
            user_id=user.id,
            kind=kind,
            value_numeric=value_numeric,
            value_text=value_text,
            recorded_at=recorded,
            data_domain="lifestyle",
            source_type=r.get("source_type") or "user-entered",
            quality_flag=r.get("quality_flag") or "self_reported",
            observed_at=observed,
            period=period,
            supersedes_id=None,
        )
        s.add(obs)
        s.flush()
        s.add(
            ObservationSourceLink(
                user_id=user.id,
                observation_id=obs.id,
                source_id=source.id,
                role="origin",
                created_at=recorded,
            )
        )
        accepted += 1
    if not dry_run:
        s.commit()
    else:
        s.rollback()
    return {"accepted": accepted, "skipped": skipped, "rejected": rejected}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import NexGene synthetic historical check-ins")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--dry-run", action="store_true", help="Validate and count only; no writes")
    parser.add_argument("--apply", action="store_true", help="Perform the import")
    parser.add_argument("--limit-days", type=int, default=None, help="Only first N day_index values")
    parser.add_argument("--email", default=SYN_EMAIL, help="Override synthetic account email")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        sys.exit(2)

    ok, reason = _env_allows_import()
    if not ok:
        print(json.dumps({"status": "refused", "reason": reason}, indent=2))
        sys.exit(1)

    dataset = load_dataset(args.dataset)
    records = list(dataset["records"])
    if args.limit_days is not None:
        records = [r for r in records if int(r.get("day_index", 0)) < args.limit_days]

    errors = validate_records(records)
    if errors:
        print(json.dumps({"status": "validation_failed", "errors": errors[:50], "error_count": len(errors)}, indent=2))
        sys.exit(1)

    import_batch_id = str(uuid.uuid4())
    manifest = {
        "status": "dry_run" if args.dry_run else "importing",
        "synthetic": True,
        "dataset_id": dataset["dataset_id"],
        "dataset_version": dataset["dataset_version"],
        "content_hash": dataset.get("content_hash"),
        "generator_version": dataset.get("generator_version"),
        "import_batch_id": import_batch_id,
        "target_email": args.email,
        "row_count": len(records),
        "database": _db_url().split("@")[-1] if "@" in _db_url() else _db_url()[:40],
        "label_warning": "SYNTHETIC DATA — not real participant observations",
    }

    engine = create_engine(_db_url(), connect_args={"check_same_thread": False} if _db_url().startswith("sqlite") else {})
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as s:
        user = ensure_user(s, dataset.get("subject_profile") or {}, email=args.email)
        source = ensure_source(s, user, dataset, import_batch_id)
        if args.dry_run:
            s.commit()  # user/source/consent may be created; observations not written
            # re-open logic: for pure dry-run of observations only, we already skip obs writes
        result = import_records(s, user, source, records, dry_run=args.dry_run)
        if not args.dry_run:
            s.commit()
        manifest.update(result)
        manifest["status"] = "dry_run_ok" if args.dry_run else "imported"
        manifest["user_id"] = user.id
        manifest["source_id"] = source.id

    out_path = HERE / f"import_manifest_{import_batch_id[:8]}.json"
    out_path.write_text(json.dumps(manifest, indent=2))
    manifest["manifest_file"] = str(out_path)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()