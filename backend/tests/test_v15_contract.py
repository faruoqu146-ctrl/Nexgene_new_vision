from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()
README = (ROOT / "README.md").read_text()


def test_v15_version_and_compartments():
    assert 'APP_VERSION = "1.9.0"' in MAIN
    assert "GENOMIC_DATABASE_URL" in MAIN
    assert "class GenomicVariant" in MAIN
    assert "class PolygenicScore" in MAIN


def test_v15_live_retrieval_surfaces():
    assert '/api/v1/evidence/live-search' in MAIN
    assert 'eutils.ncbi.nlm.nih.gov' in MAIN
    assert 'api.crossref.org/v1/works' in MAIN
    assert '/api/v1/context/live' in MAIN


def test_v15_learning_is_versioned_and_non_conversational():
    assert "class LearningRun" in MAIN
    worker = (ROOT / "scripts" / "learning_cycle.py").read_text()
    assert 'MODEL_VERSION = "plb-1.1"' in worker
    assert "deterministic personal baseline first" in worker
    assert "learning/status" in MAIN
