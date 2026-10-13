from pathlib import Path

def test_intelligence_engine_contract():
    root = Path(__file__).parents[2]
    main = (root / "backend/app/main.py").read_text()
    assert "def _pearson" in main
    assert "exploratory_association" in main
    assert "not_causal" in main
    assert "clinical_escalation" in main
    assert "/api/v1/intelligence/insights" in main
    assert "/api/v1/intelligence/data-quality" in main
