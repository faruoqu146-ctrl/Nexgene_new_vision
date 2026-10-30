"""Reproducibility receipts: canonical JSON, hashing, code fingerprint, run manifests."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .config import ENGINE_NAME, ENGINE_VERSION, MODEL_VERSION

_FP_CACHE: Optional[str] = None


def to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy / dataclass / non-finite values into plain JSON types."""
    if obj is None or isinstance(obj, (str, bool)):
        return obj
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.ndarray):
        return [to_jsonable(x) for x in obj.tolist()]
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        seq = sorted(obj, key=str) if isinstance(obj, (set, frozenset)) else obj
        return [to_jsonable(x) for x in seq]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


def _round_floats(obj: Any, sig: int = 10) -> Any:
    if isinstance(obj, float):
        return float(f"{obj:.{sig}g}")
    if isinstance(obj, dict):
        return {k: _round_floats(v, sig) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v, sig) for v in obj]
    return obj


def canonical_json(obj: Any) -> str:
    return json.dumps(_round_floats(to_jsonable(obj)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_fingerprint() -> str:
    """SHA-256 over the research package source, so results are tied to the exact code that produced them."""
    global _FP_CACHE
    if _FP_CACHE is None:
        h = hashlib.sha256()
        for p in sorted(Path(__file__).parent.glob("*.py")):
            h.update(p.name.encode())
            h.update(p.read_bytes())
        _FP_CACHE = h.hexdigest()
    return _FP_CACHE


def derive_seed(panel_digest: str, configured: Optional[int]) -> int:
    if configured is not None:
        return int(configured) % (2 ** 32)
    return int(panel_digest[:12], 16) % (2 ** 32)


def results_digest(candidates: list) -> str:
    """Hash of the decision-relevant fields of every candidate (order-independent)."""
    rows = []
    for c in candidates:
        rows.append({
            "id": c["id"], "n": c["n_pairs"], "r": c["effect"]["r_adj"], "p": c["inference"]["p_combined"],
            "q": c["inference"]["q_family_bh"], "tier": c["tier"]["level"], "status": c["status"],
        })
    rows.sort(key=lambda r: r["id"])
    return sha256_hex(canonical_json(rows))


def make_manifest(*, panel_digest: str, config_digest: str, seed: int, results_hash: str,
                  prev_run_hash: Optional[str] = None, window: Optional[dict] = None) -> dict:
    body = {
        "engine": ENGINE_NAME, "engine_version": ENGINE_VERSION, "model_version": MODEL_VERSION,
        "code_fingerprint": code_fingerprint(), "input_hash": panel_digest, "config_hash": config_digest,
        "seed": seed, "results_hash": results_hash, "prev_run_hash": prev_run_hash,
        "numpy_version": np.__version__, "window": window or {},
    }
    body["run_hash"] = sha256_hex(canonical_json({k: v for k, v in body.items() if k != "numpy_version"}))
    return body


def verify_chain(manifests: list, allow_truncated: bool = True) -> dict:
    """Check that each manifest's prev_run_hash equals the previous run_hash and its own hash is self-consistent.

    With ``allow_truncated`` the first manifest is treated as an anchor (its predecessor may not be in the window).
    """
    problems = []
    prev = None
    for i, m in enumerate(manifests):
        body = {k: v for k, v in m.items() if k not in ("run_hash", "numpy_version")}
        recomputed = sha256_hex(canonical_json(body))
        if recomputed != m.get("run_hash"):
            problems.append({"index": i, "problem": "run_hash_mismatch"})
        if i > 0 or not allow_truncated:
            if m.get("prev_run_hash") != prev:
                problems.append({"index": i, "problem": "chain_break"})
        prev = m.get("run_hash")
    return {"ok": not problems, "problems": problems, "length": len(manifests)}

