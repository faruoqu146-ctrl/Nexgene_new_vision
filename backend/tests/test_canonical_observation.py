from datetime import datetime, timezone
from backend.app.governance.models_contract import observation_from_checkin


def test_checkin_maps_to_lifestyle_canonical():
    ts = datetime(2026, 10, 19, 8, 0, tzinfo=timezone.utc)
    obs = observation_from_checkin(
        subject_id=1, kind="energy", value=7.5, recorded_at=ts, period="morning"
    )
    assert obs.data_domain == "lifestyle"
    assert obs.observation_type == "energy"
    assert obs.source_type == "user-entered"
    assert obs.value_type == "numeric"
    assert obs.value == 7.5
    assert "collect" in obs.consent_purposes
    assert obs.metadata["period"] == "morning"


def test_text_value_type():
    ts = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)
    obs = observation_from_checkin(
        subject_id=1, kind="morning_context", value="slept poorly", recorded_at=ts
    )
    assert obs.value_type == "text"
