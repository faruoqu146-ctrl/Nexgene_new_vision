"""Assemble backend/app/main.py from scripts/main_payload/part_*.b64
Exact ZIP content; verified by sha256.
Run from repo root:  python scripts/assemble_main.py
"""
from __future__ import annotations
import base64, gzip, hashlib
from pathlib import Path

EXPECTED = "9568e33573106d2e1db96431b498561c6bedc5ae8afc84e344afac0e3d9c70f9"

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    payload = root / "scripts" / "main_payload"
    parts = sorted(payload.glob("part_*.b64"))
    if not parts:
        raise SystemExit(f"no part_*.b64 under {payload}")
    b64 = "".join(p.read_text().strip() for p in parts)
    data = gzip.decompress(base64.b64decode(b64))
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED:
        raise SystemExit(f"hash mismatch: {digest}")
    target = root / "backend" / "app" / "main.py"
    target.write_bytes(data)
    print(f"wrote {target} ({len(data)} bytes, sha256={digest})")

if __name__ == "__main__":
    main()
