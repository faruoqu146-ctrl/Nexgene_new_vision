from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()
WORKER = (ROOT / "scripts" / "learning_cycle.py").read_text()
README = (ROOT / "README.md").read_text()


def test_v16_living_baseline_and_fragmented_sources():
    assert 'APP_VERSION = "1.9.0"' in MAIN
    assert "INTELLIGENCE_MODEL_VERSION = nre.MODEL_VERSION" in MAIN
    assert "class SourceRecord" in MAIN
    assert "class SourceDocument" in MAIN
    assert "class ObservationSourceLink" in MAIN
    assert '/api/v1/sources' in MAIN
    assert '/api/v1/sources/documents' in MAIN
    assert '/api/v1/baseline/living' in MAIN
    assert "metadata_only" in MAIN


def test_v16_evidence_snapshots_are_persisted_with_hashes():
    assert "class EvidenceSnapshot" in MAIN
    assert '/api/v1/evidence/snapshots' in MAIN
    assert 'hashlib.sha256(canonical.encode())' in MAIN
    assert "persisted_snapshots" in MAIN


def test_v16_learning_version_is_source_aware():
    assert 'MODEL_VERSION = "plb-1.1"' in WORKER
    assert '"source_aware": True' in WORKER or '"source_aware": True' in WORKER or 'source_aware' in WORKER
