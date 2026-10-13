import json
import math

import numpy as np

from _research_helpers import ROOT  # noqa: F401
from backend.app.research.provenance import (
    canonical_json, code_fingerprint, derive_seed, make_manifest, results_digest, sha256_hex, to_jsonable, verify_chain,
)


def test_json_conversion_handles_numpy_and_non_finite_values():
    obj = {"a": np.float64(1.5), "b": np.int64(3), "c": float("nan"), "d": [np.inf, -np.inf, 2.0], "e": np.array([1, 2]), "f": np.bool_(True), "g": (1, 2)}
    out = to_jsonable(obj)
    assert out == {"a": 1.5, "b": 3, "c": None, "d": [None, None, 2.0], "e": [1, 2], "f": True, "g": [1, 2]}
    json.dumps(out, allow_nan=False)


def test_canonical_json_is_order_independent_and_rounds_float_noise():
    assert canonical_json({"b": 1, "a": 2.0}) == canonical_json({"a": 2.0, "b": 1})
    assert canonical_json({"x": 0.1 + 0.2}) == canonical_json({"x": 0.3})


def test_seed_is_deterministic_and_overridable():
    h = sha256_hex("input")
    assert derive_seed(h, None) == derive_seed(h, None) and derive_seed(h, 5) == 5 and derive_seed(sha256_hex("other"), None) != derive_seed(h, None)


def test_code_fingerprint_is_a_stable_sha256():
    fp = code_fingerprint()
    assert len(fp) == 64 and fp == code_fingerprint()


def _chain(n=4):
    out, prev = [], None
    for i in range(n):
        m = make_manifest(panel_digest=sha256_hex(f"data{i}"), config_digest=sha256_hex("cfg"), seed=i, results_hash=sha256_hex(f"res{i}"), prev_run_hash=prev)
        out.append(m)
        prev = m["run_hash"]
    return out


def test_manifest_chain_verifies_and_detects_tampering_and_breaks():
    chain = _chain()
    assert verify_chain(chain)["ok"]
    assert verify_chain(chain[1:])["ok"]                         # a truncated window is anchored at its first manifest
    assert not verify_chain(chain[1:], allow_truncated=False)["ok"]
    forged = [dict(m) for m in chain]
    forged[2]["results_hash"] = sha256_hex("different")
    bad = verify_chain(forged)
    assert not bad["ok"] and any(p["problem"] == "run_hash_mismatch" for p in bad["problems"])
    reordered = [chain[0], chain[2], chain[1], chain[3]]
    assert any(p["problem"] == "chain_break" for p in verify_chain(reordered)["problems"])


def test_numpy_version_is_recorded_but_not_part_of_the_hash():
    m = _chain(1)[0]
    assert m["numpy_version"] == np.__version__
    assert verify_chain([{**m, "numpy_version": "0.0.0"}])["ok"]


def test_results_digest_ignores_candidate_order():
    def c(i, r):
        return {"id": i, "n_pairs": 30, "effect": {"r_adj": r}, "inference": {"p_combined": 0.1, "q_family_bh": 0.2}, "tier": {"level": 1}, "status": "TESTING"}
    a = [c("a", 0.3), c("b", 0.4)]
    assert results_digest(a) == results_digest(list(reversed(a))) and results_digest(a) != results_digest([c("a", 0.31), c("b", 0.4)])
