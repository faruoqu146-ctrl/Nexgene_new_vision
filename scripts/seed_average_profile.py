"""Seed an average-person demo account with 90 consecutive days of check-ins.

DEVELOPMENT ONLY.
Safe to call multiple times: if the demo email already exists, it is left unchanged.

Must never run under production configuration:
  - Requires DEV_MODE=true or ALLOW_DEMO_SEED=true
  - Refuses otherwise with status=refused
  - Credentials are not printed when DEV_MODE is false

Synthetic records are tagged as demo/synthetic in source metadata.
"""
from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone

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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

DEMO_EMAIL = "average.person@nexgene.demo"
DEMO_PASSWORD = "AveragePerson1!"
DAYS = 90

pwd = CryptContext(
    schemes=["pbkdf2_sha256"],
    pbkdf2_sha256__default_rounds=600000,
    deprecated="auto",
)


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


class ObservationSourceLink(Base):
    __tablename__ = "observation_source_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_records.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="origin")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _round1(x: float) -> float:
    return round(x, 1)


def _generate_day(rng: random.Random, day_index: int, weekday: int, prev_sleep: float) -> dict[str, float | str]:
    """Synthetic but plausible 'average adult' daily signals with mild structure."""
    workday = weekday < 5
    stress_base = 5.2 if workday else 3.8
    if weekday == 0:
        stress_base += 0.8
    if weekday == 4:
        stress_base += 0.3

    sleep_duration = _clamp(rng.gauss(7.1 if workday else 7.8, 0.55), 5.0, 9.5)
    sleep_debt = max(0.0, 7.0 - prev_sleep)
    energy = _clamp(rng.gauss(6.3 - 0.35 * sleep_debt, 1.0), 2.0, 10.0)
    sleep_quality = _clamp(rng.gauss(6.5 + 0.25 * (sleep_duration - 7.0), 1.1), 2.0, 10.0)
    stress = _clamp(rng.gauss(stress_base, 1.2), 1.0, 9.0)
    mood = _clamp(rng.gauss(6.4 - 0.25 * (stress - 5.0) + 0.15 * (energy - 6.0), 1.0), 2.0, 10.0)
    focus = _clamp(rng.gauss(6.2 - 0.3 * (stress - 5.0) + 0.2 * (sleep_duration - 7.0), 1.1), 2.0, 10.0)
    activity_level = _clamp(rng.gauss(5.5 if workday else 6.2, 1.4), 0.0, 10.0)
    diet_quality = _clamp(rng.gauss(6.0 if workday else 5.5, 1.3), 2.0, 10.0)
    caffeine = float(rng.choice([0, 1, 1, 1, 2, 2, 3]) if workday else rng.choice([0, 0, 1, 1, 2]))
    if workday:
        alcohol = float(rng.choice([0, 0, 0, 0, 0, 1]))
    else:
        alcohol = float(rng.choice([0, 0, 1, 1, 2, 2, 3]))
    nicotine = 0.0

    morning_context = "none"
    if rng.random() < 0.08:
        morning_context = rng.choice(["headache", "fatigue", "pain"])
    elif rng.random() < 0.05:
        morning_context = "skipped"

    return {
        "sleep_duration": _round1(sleep_duration),
        "sleep_quality": _round1(sleep_quality),
        "energy": _round1(energy),
        "morning_context": morning_context,
        "mood": _round1(mood),
        "stress": _round1(stress),
        "focus": _round1(focus),
        "activity_level": _round1(activity_level),
        "diet_quality": _round1(diet_quality),
        "caffeine": caffeine,
        "alcohol": alcohol,
        "nicotine": nicotine,
    }


def ensure_average_demo() -> dict:
    """Create the demo user + profile + 90 days of observations if missing.

    Development-only. Refuses when production-like configuration is active.
    """
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    allow = os.getenv("ALLOW_DEMO_SEED", "false").lower() == "true"
    if not dev_mode and not allow:
        return {
            "status": "refused",
            "reason": "Demo seeding is disabled unless DEV_MODE=true or ALLOW_DEMO_SEED=true",
        }
    database_url = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
    )
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    s: Session = SessionLocal()
    try:
        existing = s.scalar(select(User).where(User.email == DEMO_EMAIL))
        if existing:
            return {"status": "exists", "email": DEMO_EMAIL, "user_id": existing.id}

        now = datetime.now(timezone.utc)
        user = User(
            email=DEMO_EMAIL,
            password_hash=pwd.hash(DEMO_PASSWORD),
            created_at=now - timedelta(days=DAYS),
            email_verified=True,
            ai_analysis_enabled=False,
        )
        s.add(user)
        s.flush()

        profile = Profile(
            user_id=user.id,
            age_range="30-39",
            country="Nigeria",
            occupation="Office professional",
            student=False,
            study_field=None,
            schedule="standard",
            timezone="Africa/Lagos",
            location_city="Kano",
            live_context_enabled=True,
            updated_at=now,
        )
        s.add(profile)

        source = SourceRecord(
            user_id=user.id,
            source_type="self_reported",
            label="NexGene check-ins",
            status="active",
            reliability="self_reported",
            metadata_json=json.dumps({"periods": ["morning", "evening"], "seed": "average_person_v1", "synthetic": True, "demo": True}),
            created_at=now - timedelta(days=DAYS),
        )
        s.add(source)
        s.flush()

        rng = random.Random(20261015)
        prev_sleep = 7.0
        start = (now - timedelta(days=DAYS - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        obs_count = 0

        for d in range(DAYS):
            day = start + timedelta(days=d)
            weekday = day.weekday()
            values = _generate_day(rng, d, weekday, prev_sleep)
            prev_sleep = float(values["sleep_duration"])

            morning_at = day.replace(hour=7, minute=15, second=0) + timedelta(minutes=rng.randint(0, 40))
            evening_at = day.replace(hour=21, minute=10, second=0) + timedelta(minutes=rng.randint(0, 50))

            morning_kinds = ("sleep_duration", "sleep_quality", "energy", "morning_context")
            evening_kinds = (
                "mood", "stress", "focus", "activity_level",
                "diet_quality", "caffeine", "alcohol", "nicotine",
            )

            for kinds, when in ((morning_kinds, morning_at), (evening_kinds, evening_at)):
                for kind in kinds:
                    value = values[kind]
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        obs = Observation(
                            user_id=user.id,
                            kind=kind,
                            value_numeric=float(value),
                            value_text=None,
                            recorded_at=when if when.tzinfo else when.replace(tzinfo=timezone.utc),
                        )
                    else:
                        obs = Observation(
                            user_id=user.id,
                            kind=kind,
                            value_numeric=None,
                            value_text=str(value),
                            recorded_at=when if when.tzinfo else when.replace(tzinfo=timezone.utc),
                        )
                    s.add(obs)
                    s.flush()
                    s.add(
                        ObservationSourceLink(
                            user_id=user.id,
                            observation_id=obs.id,
                            source_id=source.id,
                            role="origin",
                            created_at=obs.recorded_at,
                        )
                    )
                    obs_count += 1

        s.commit()
        return {
            "status": "created",
            "email": DEMO_EMAIL,
            "password": DEMO_PASSWORD,
            "user_id": user.id,
            "days": DAYS,
            "observations": obs_count,
        }
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


if __name__ == "__main__":
    result = ensure_average_demo()
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"
    safe = {k: v for k, v in result.items() if k != "password"}
    if result.get("status") == "created" and dev_mode:
        print(json.dumps(result))
    else:
        print(json.dumps(safe))
