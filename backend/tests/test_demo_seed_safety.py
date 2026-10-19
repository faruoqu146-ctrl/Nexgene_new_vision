"""Production safety for demo seeding."""
import os
import importlib
import sys
from pathlib import Path

# Ensure project root importable
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_seed_refuses_without_dev_mode(monkeypatch, tmp_path):
    db = tmp_path / "prod.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)
    # Fresh import path
    import scripts.seed_average_profile as seed
    importlib.reload(seed)
    result = seed.ensure_average_demo()
    assert result["status"] == "refused"
    assert "DEV_MODE" in result.get("reason", "")


def test_seed_allowed_in_dev_mode(monkeypatch, tmp_path):
    db = tmp_path / "dev.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("DEV_MODE", "true")
    monkeypatch.delenv("ALLOW_DEMO_SEED", raising=False)
    import scripts.seed_average_profile as seed
    importlib.reload(seed)
    result = seed.ensure_average_demo()
    assert result["status"] in ("created", "exists")
    if result["status"] == "created":
        assert result.get("email") == seed.DEMO_EMAIL
        # credentials may be present in created response for local use only
        assert "password" in result


def test_seed_allowed_with_explicit_flag(monkeypatch, tmp_path):
    db = tmp_path / "flag.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db}")
    monkeypatch.setenv("DEV_MODE", "false")
    monkeypatch.setenv("ALLOW_DEMO_SEED", "true")
    import scripts.seed_average_profile as seed
    importlib.reload(seed)
    result = seed.ensure_average_demo()
    assert result["status"] in ("created", "exists")


def test_dockerfile_does_not_unconditionally_seed():
    docker = (ROOT / "Dockerfile").read_text()
    # Must gate seed; must not be bare unconditional seed
    assert "seed_average_profile" in docker
    assert "DEV_MODE" in docker
    assert "Skipping demo seed" in docker or "ALLOW_DEMO_SEED" in docker


def test_compose_places_all_sqlite_dbs_on_volume():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "sqlite:////data/nexgene.db" in compose
    assert "sqlite:////data/nexgene_clinical.db" in compose
    assert "sqlite:////data/nexgene_genomic.db" in compose
    assert "nexgene_data:/data" in compose
