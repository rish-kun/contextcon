"""Country-code normalisation in case inputs, and the policy-refresh reason."""

from app.pipelines.evaluate.inputs import _field_value
from app.pipelines.evaluate.refresh import refresh_reason
from app.rules import policy


def test_iso_country_code_reads_as_country_name():
    assert _field_value("locations.country", "IND") == "India"
    assert _field_value("headcount.largest_headcount_country", "USA") == "United States"
    assert _field_value("locations.country", "India") == "India"


def test_unknown_country_code_is_unknown_not_a_mismatch():
    assert _field_value("locations.country", "ZZZ") is None


def test_other_fields_untouched():
    assert _field_value("basic_info.company_type", "IND") == "IND"


def test_refresh_reason_names_the_country_fix():
    assert refresh_reason("2026-11-22.3").startswith("policy fix: country code normalisation")
    assert refresh_reason(policy.POLICY_VERSION).startswith("policy update")
    assert len(refresh_reason(None)) <= 64
