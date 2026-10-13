from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()


def test_engine_version_markers():
    assert 'APP_VERSION = "1.9.0"' in MAIN
    assert "nre-0.4.0-research-core" in MAIN or "MODEL_VERSION" in MAIN
