from backend.app.governance.consent import (
    ALL_PURPOSES,
    DEFAULT_LIFESTYLE_PURPOSES,
    PURPOSE_COLLECT,
    PURPOSE_PERSONAL_INSIGHT,
    PURPOSE_RESEARCH,
    PURPOSE_CROSS_DOMAIN,
    consent_allows,
    missing_purposes,
    normalize_purposes,
)


def test_normalize_filters_unknown_and_case():
    assert normalize_purposes(["Collect", "research", "not-a-purpose"]) == {
        PURPOSE_COLLECT, PURPOSE_RESEARCH
    }


def test_default_lifestyle_allows_personal_not_research():
    assert consent_allows(DEFAULT_LIFESTYLE_PURPOSES, PURPOSE_COLLECT)
    assert consent_allows(DEFAULT_LIFESTYLE_PURPOSES, PURPOSE_PERSONAL_INSIGHT)
    assert not consent_allows(DEFAULT_LIFESTYLE_PURPOSES, PURPOSE_RESEARCH)
    assert not consent_allows(DEFAULT_LIFESTYLE_PURPOSES, PURPOSE_CROSS_DOMAIN)


def test_missing_purposes():
    granted = {PURPOSE_COLLECT}
    assert missing_purposes(granted, [PURPOSE_COLLECT, PURPOSE_RESEARCH]) == {PURPOSE_RESEARCH}


def test_all_purposes_stable():
    assert PURPOSE_COLLECT in ALL_PURPOSES
    assert len(ALL_PURPOSES) >= 6
