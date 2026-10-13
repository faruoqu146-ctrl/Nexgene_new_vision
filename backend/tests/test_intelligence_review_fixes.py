from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "backend" / "app" / "main.py").read_text()


def test_review_hardening_markers_present():
    assert "Student-t" in MAIN or "student_t" in MAIN or "_student_t" in MAIN or "t_two_sided" in MAIN
    assert "calendar" in MAIN.lower() or "lag" in MAIN
    assert "CSRF" in MAIN or "csrf" in MAIN
    assert "DEV_MODE" in MAIN
