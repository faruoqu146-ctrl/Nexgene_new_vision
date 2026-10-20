from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()
WORKER = (ROOT / "scripts" / "learning_cycle.py").read_text()


def test_intelligence_engine_contract():
    assert 'APP_VERSION = "1.9.3"' in MAIN
    assert "INTELLIGENCE_MODEL_VERSION = nre.MODEL_VERSION" in MAIN
    for cls in ("Hypothesis", "HypothesisTest", "Prediction", "PhenotypeDefinition", "PhenotypeObservation", "Experiment"):
        assert f"class {cls}" in MAIN
    for route in ('/api/v1/intelligence/engine/run', '/api/v1/intelligence/hypotheses', '/api/v1/intelligence/predictions',
                  '/api/v1/intelligence/audit/{hypothesis_id}', '/api/v1/intelligence/research/brief',
                  '/api/v1/intelligence/experiments'):
        assert route in MAIN
    for phrase in ("Benjamini-Hochberg", "Spearman", "empirical-Bayes", "E-value", "evidence readiness levels"):
        assert phrase in MAIN


def test_existing_learning_worker_remains_compatible():
    assert 'MODEL_VERSION = "plb-1.1"' in WORKER
    assert 'source_aware' in WORKER
    assert "run_intelligence_engine" in WORKER


def test_engine_is_a_package_not_a_script_inside_main():
    pkg = ROOT / "backend" / "app" / "research"
    for module in ("inference.py", "discovery.py", "gates.py", "forecast.py", "experiment.py", "spc.py", "bayes.py",
                   "multiplicity.py", "provenance.py", "panel.py", "narrative.py", "simulate.py", "validate.py"):
        assert (pkg / module).exists(), module
    assert len(MAIN.splitlines()) < 4500  # monolith growth guard; engine remains in backend.app.research
