"""Legacy v1.3 contract checks retained for regression visibility."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "backend" / "app" / "main.py"


def test_v130_contract():
    main = MAIN.read_text()
    assert 'APP_VERSION = "1.9.4"' in main
