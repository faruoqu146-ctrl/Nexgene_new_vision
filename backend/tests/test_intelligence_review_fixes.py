from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()
FORECAST = (ROOT / "backend" / "app" / "research" / "forecast.py").read_text()


def test_prediction_track_record_is_persistent():
    assert "hits: Mapped[int]" in MAIN
    assert "misses: Mapped[int]" in MAIN
    assert "inconclusive_count: Mapped[int]" in MAIN
    assert "_evaluate_forward_tests" in MAIN and "nre.score_frozen" in MAIN and "nre.summarize_track" in MAIN


def test_predictions_are_locked_models_with_local_level_baselines():
    assert "Y_WINDOW = 14" in FORECAST and "X_WINDOW = 28" in FORECAST
    assert "nre.freeze_model" in MAIN and "nre.preregistration" in MAIN and "verify_forecast_preregistration" in MAIN
    assert "legacy_or_unverifiable_prediction_superseded_by_locked_model_protocol" in MAIN


def test_evidence_snapshots_are_user_scoped():
    assert 'user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)' in MAIN
    assert "EvidenceSnapshot.user_id == u.id" in MAIN


def test_engine_run_is_protected_and_rate_limited():
    assert 'require_csrf(request, st)' in MAIN
    assert 'rate_limit(request, f"intelligence-engine:{u.id}", 3, s)' in MAIN
    assert "INTELLIGENCE_RUN_COOLDOWN_SECONDS" in MAIN
