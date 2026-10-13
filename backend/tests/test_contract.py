from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()


def test_core_api_surface():
    for path in [
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/checkins/morning",
        "/api/v1/checkins/evening",
        "/api/v1/intelligence/engine/run",
        "/api/v1/intelligence/research/brief",
        "/api/v1/intelligence/experiments",
    ]:
        assert path in MAIN
