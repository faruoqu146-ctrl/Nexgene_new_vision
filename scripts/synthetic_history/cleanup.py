#!/usr/bin/env python3
"""Scoped cleanup for synthetic historical imports only.

Deletes observations linked to synthetic source labels for the dedicated test account.
Requires DEV_MODE=true or ALLOW_SYNTHETIC_IMPORT=true.

Usage:
  python scripts/synthetic_history/cleanup.py --dry-run
  python scripts/synthetic_history/cleanup.py --apply --confirm SYNTHETIC
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

SYN_EMAIL = os.getenv("SYNTHETIC_IMPORT_EMAIL", "synthetic.student@nexgene.test")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)


class SourceRecord(Base):
    __tablename__ = "source_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


class Observation(Base):
    __tablename__ = "observations"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)


class ObservationSourceLink(Base):
    __tablename__ = "observation_source_links"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    observation_id: Mapped[int] = mapped_column(Integer, index=True)
    source_id: Mapped[int] = mapped_column(Integer, index=True)


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./nexgene.db")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


def _env_allows_import() -> tuple[bool, str]:
    dev = os.getenv("DEV_MODE", "false").lower() == "true"
    allow = os.getenv("ALLOW_SYNTHETIC_IMPORT", "false").lower() == "true"
    if dev or allow:
        return True, "allowed"
    return False, "Refused: set DEV_MODE=true or ALLOW_SYNTHETIC_IMPORT=true"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="", help="Must be SYNTHETIC when --apply")
    parser.add_argument("--email", default=SYN_EMAIL)
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("Specify --dry-run or --apply", file=sys.stderr)
        sys.exit(2)
    ok, reason = _env_allows_import()
    if not ok:
        print(json.dumps({"status": "refused", "reason": reason}))
        sys.exit(1)
    if args.apply and args.confirm != "SYNTHETIC":
        print(json.dumps({"status": "refused", "reason": "Pass --confirm SYNTHETIC to apply cleanup"}))
        sys.exit(1)

    engine = create_engine(
        _db_url(),
        connect_args={"check_same_thread": False} if _db_url().startswith("sqlite") else {},
    )
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        user = s.scalar(select(User).where(User.email == args.email))
        if user is None:
            print(json.dumps({"status": "ok", "deleted_observations": 0, "note": "user not found"}))
            return
        sources = s.scalars(
            select(SourceRecord).where(
                SourceRecord.user_id == user.id,
                SourceRecord.label.like("SYNTHETIC %"),
            )
        ).all()
        source_ids = [x.id for x in sources]
        if not source_ids:
            print(json.dumps({"status": "ok", "deleted_observations": 0, "note": "no synthetic sources"}))
            return
        links = s.scalars(
            select(ObservationSourceLink).where(
                ObservationSourceLink.user_id == user.id,
                ObservationSourceLink.source_id.in_(source_ids),
            )
        ).all()
        obs_ids = sorted({lnk.observation_id for lnk in links})
        report = {
            "status": "dry_run" if args.dry_run else "deleted",
            "synthetic": True,
            "email": args.email,
            "source_count": len(source_ids),
            "observation_count": len(obs_ids),
            "source_ids": source_ids,
        }
        if args.dry_run:
            print(json.dumps(report, indent=2))
            return
        if obs_ids:
            s.execute(
                delete(ObservationSourceLink).where(
                    ObservationSourceLink.user_id == user.id,
                    ObservationSourceLink.observation_id.in_(obs_ids),
                )
            )
            s.execute(
                delete(Observation).where(
                    Observation.user_id == user.id,
                    Observation.id.in_(obs_ids),
                )
            )
        for src in sources:
            src.status = "deleted"
            try:
                meta = json.loads(src.metadata_json or "{}")
            except Exception:
                meta = {}
            meta["deleted_at"] = datetime.now(timezone.utc).isoformat()
            src.metadata_json = json.dumps(meta)
        s.commit()
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
