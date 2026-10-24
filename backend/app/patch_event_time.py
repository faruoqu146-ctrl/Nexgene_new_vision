#!/usr/bin/env python3
"""Apply event-time (observed_at) fixes to main.py at container start."""
from __future__ import annotations

from pathlib import Path

MAIN = Path(__file__).resolve().parent / "main.py"

OLD_TODAY = (
    "@app.get(\"/api/v1/today\")\n"
    "def today(u: User = Depends(current_user), s: Session = Depends(db)):\n"
    "    since = now() - timedelta(hours=24)\n"
    "    try:\n"
    "        rows = s.scalars(select(Observation).where(Observation.user_id == u.id, Observation.recorded_at >= since).order_by(Observation.recorded_at.desc())).all()\n"
    "    except Exception:\n"
    "        s.rollback()\n"
    "        rows = []\n"
    "    out = {}\n"
    "    for r in rows:\n"
    "        out.setdefault(r.kind, r.value_numeric if r.value_numeric is not None else r.value_text)\n"
    "    return out\n"
)

NEW_TODAY = (
    "@app.get(\"/api/v1/today\")\n"
    "def today(u: User = Depends(current_user), s: Session = Depends(db)):\n"
    "    since = now() - timedelta(hours=24)\n"
    "    try:\n"
    "        rows = s.scalars(select(Observation).where(Observation.user_id == u.id).order_by(Observation.recorded_at.desc()).limit(500)).all()\n"
    "    except Exception:\n"
    "        s.rollback()\n"
    "        rows = []\n"
    "    out = {}\n"
    "    for r in rows:\n"
    "        event = r.observed_at or r.recorded_at\n"
    "        if event is None or event < since:\n"
    "            continue\n"
    "        out.setdefault(r.kind, r.value_numeric if r.value_numeric is not None else r.value_text)\n"
    "    return out\n"
)

OLD_TL = (
    "@app.get(\"/api/v1/timeline\")\n"
    "def timeline(u: User = Depends(current_user), s: Session = Depends(db)):\n"
    "    rows = s.scalars(select(Observation).where(Observation.user_id == u.id).order_by(Observation.recorded_at.desc()).limit(300)).all()\n"
    "    return [{\"kind\": r.kind, \"value\": r.value_numeric if r.value_numeric is not None else r.value_text, \"recorded_at\": r.recorded_at.isoformat()} for r in rows]\n"
)

NEW_TL = (
    "@app.get(\"/api/v1/timeline\")\n"
    "def timeline(u: User = Depends(current_user), s: Session = Depends(db)):\n"
    "    rows = s.scalars(select(Observation).where(Observation.user_id == u.id).order_by(Observation.observed_at.desc().nulls_last(), Observation.recorded_at.desc()).limit(300)).all()\n"
    "    out = []\n"
    "    for r in rows:\n"
    "        event = r.observed_at or r.recorded_at\n"
    "        out.append({\n"
    "            \"kind\": r.kind,\n"
    "            \"value\": r.value_numeric if r.value_numeric is not None else r.value_text,\n"
    "            \"recorded_at\": r.recorded_at.isoformat() if r.recorded_at else None,\n"
    "            \"observed_at\": r.observed_at.isoformat() if r.observed_at else None,\n"
    "            \"event_at\": event.isoformat() if event else None,\n"
    "            \"period\": r.period,\n"
    "        })\n"
    "    return out\n"
)

OLD_PAT = (
    "@app.get(\"/api/v1/patterns\")\n"
    "def patterns(days: int = 30, u: User = Depends(current_user), s: Session = Depends(db)):\n"
    "    days = max(7, min(days, 90))\n"
    "    since = now() - timedelta(days=days)\n"
    "    rows = s.scalars(select(Observation).where(Observation.user_id == u.id, Observation.recorded_at >= since).order_by(Observation.recorded_at.asc())).all()\n"
    "    buckets = defaultdict(lambda: defaultdict(list))\n"
    "    for r in rows:\n"
    "        if r.value_numeric is not None:\n"
    "            buckets[r.recorded_at.date().isoformat()][r.kind].append(r.value_numeric)\n"
)

NEW_PAT = (
    "@app.get(\"/api/v1/patterns\")\n"
    "def patterns(days: int = 30, u: User = Depends(current_user), s: Session = Depends(db)):\n"
    "    days = max(7, min(days, 90))\n"
    "    since = now() - timedelta(days=days)\n"
    "    rows = s.scalars(select(Observation).where(Observation.user_id == u.id).order_by(Observation.recorded_at.asc()).limit(5000)).all()\n"
    "    buckets = defaultdict(lambda: defaultdict(list))\n"
    "    for r in rows:\n"
    "        if r.value_numeric is None:\n"
    "            continue\n"
    "        event = r.observed_at or r.recorded_at\n"
    "        if event is None or event < since:\n"
    "            continue\n"
    "        buckets[event.date().isoformat()][r.kind].append(r.value_numeric)\n"
)


def main() -> int:
    if not MAIN.exists():
        print("patch_event_time: main.py not found at", MAIN)
        return 0
    src = MAIN.read_text()
    n = 0
    for old, new, name in (
        (OLD_TODAY, NEW_TODAY, "today"),
        (OLD_TL, NEW_TL, "timeline"),
        (OLD_PAT, NEW_PAT, "patterns"),
    ):
        if old in src:
            src = src.replace(old, new, 1)
            n += 1
            print(f"patch_event_time: applied {name}")
        elif name == "timeline" and "event_at" in src:
            print(f"patch_event_time: {name} already patched")
        else:
            print(f"patch_event_time: {name} pattern not found")
    if n:
        MAIN.write_text(src)
        print(f"patch_event_time: wrote {n} replacements")
    else:
        print("patch_event_time: no changes written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
