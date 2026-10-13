"""Static contract checks on main.py's research-engine integration (no web stack needed)."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()
TREE = ast.parse(MAIN)
REQ = (ROOT / "backend" / "requirements.txt").read_text().lower()


def _routes():
    out = []
    for node in TREE.body:
        if isinstance(node, ast.FunctionDef):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name) and d.func.value.id == "app":
                    if d.args and isinstance(d.args[0], ast.Constant):
                        out.append((d.func.attr, d.args[0].value, node))
    return out


def test_version_and_engine_wiring():
    assert 'APP_VERSION = "1.9.0"' in MAIN
    assert "from . import research as nre" in MAIN and "INTELLIGENCE_MODEL_VERSION = nre.MODEL_VERSION" in MAIN
    assert "numpy" in REQ and "tzdata" in REQ


def test_new_endpoints_exist():
    paths = {(m, p) for m, p, _ in _routes()}
    for want in [("post", "/api/v1/intelligence/engine/run"), ("get", "/api/v1/intelligence/engine/status"),
                 ("get", "/api/v1/intelligence/hypotheses"), ("get", "/api/v1/intelligence/predictions"),
                 ("get", "/api/v1/intelligence/audit/{hypothesis_id}"), ("get", "/api/v1/intelligence/research/brief"),
                 ("get", "/api/v1/intelligence/research/manifest"), ("post", "/api/v1/intelligence/experiments"),
                 ("get", "/api/v1/intelligence/experiments"), ("get", "/api/v1/intelligence/experiments/{experiment_id}"),
                 ("post", "/api/v1/intelligence/experiments/{experiment_id}/analyze"),
                 ("post", "/api/v1/intelligence/experiments/{experiment_id}/abandon")]:
        assert want in paths, want


def test_every_intelligence_post_is_csrf_protected_and_every_route_requires_a_user():
    for method, path, node in _routes():
        if not path.startswith("/api/v1/intelligence/"):
            continue
        src = ast.get_source_segment(MAIN, node)
        assert "current_user" in src, path                       # authenticated
        if method == "post":
            assert "require_csrf(request, st)" in src, path      # CSRF-protected
    for path in ("engine/run", "experiments\"", "analyze"):
        pass
    assert 'rate_limit(request, f"intelligence-engine:{u.id}", 3, s)' in MAIN
    assert 'rate_limit(request, f"experiment-create:{u.id}"' in MAIN and 'rate_limit(request, f"experiment-analyze:{u.id}"' in MAIN


def test_every_experiment_and_hypothesis_query_is_scoped_to_the_user():
    for needle in ("Experiment.user_id == u.id", "Hypothesis.user_id == u.id", "Prediction.user_id == u.id"):
        assert needle in MAIN
    src = ast.get_source_segment(MAIN, next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_get_experiment"))
    assert "Experiment.user_id == u.id" in src and "404" in src


def test_legacy_correlation_engine_is_gone():
    for name in ("_lag_pairs", "_normal_p_from_r", "_dependence_preserving_permutation_p", "_hypothesis_status_with_track_record",
                 "_evaluate_pending_predictions", "abs(r) < 0.30"):
        assert name not in MAIN, name


def test_naive_sqlite_datetimes_are_never_interpreted_as_server_local_time():
    assert "def _utc(dt)" in MAIN
    ds = ast.get_source_segment(MAIN, next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_daily_series"))
    assert "tzinfo is not None" in ds and "replace(tzinfo=timezone.utc)" in ds


def test_only_one_active_experiment_at_a_time():
    src = ast.get_source_segment(MAIN, next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "create_experiment"))
    assert '"DESIGNED", "RUNNING"' in src and "409" in src


def test_experiment_table_and_preregistration_are_persisted():
    assert "class Experiment(Base)" in MAIN and "preregistration_hash" in MAIN and "design_json" in MAIN


def test_epistemic_boundary_and_escalation_flag_are_preserved():
    assert "do not establish causation, diagnosis, treatment" in MAIN and '"clinical_escalation": "not_assessed"' in MAIN
