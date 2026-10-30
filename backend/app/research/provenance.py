"""Provenance helpers (boot-safe stub)."""
from __future__ import annotations
import hashlib
import json
from typing import Any

def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, default=str, separators=(",", ":"))

def code_fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)

def verify_chain(*args, **kwargs):
    return {"ok": True, "status": "stub"}
