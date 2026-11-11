import pandas as pd
import pytest

from datascope.pii import _luhn_valid, detect_sensitive_data, mask_value


class TestLuhn:
    def test_valid_test_card_number(self):
        assert _luhn_valid("4532015112830366") is True

    def test_invalid_checksum(self):
        assert _luhn_valid("1234567890123456") is False

    def test_too_short_is_invalid(self):
        assert _luhn_valid("123456") is False

    def test_ignores_non_digit_characters(self):
        assert _luhn_valid("4532-0151-1283-0366") is True


class TestMaskValue:
    def test_email_masking_keeps_first_char_and_tld(self):
        assert mask_value("john.doe@example.com") == "j***@***.com"

    def test_short_value_fully_masked(self):
        assert mask_value("abc") == "***"

    def test_long_value_keeps_first_and_last_char(self):
        masked = mask_value("5551234567")
        assert masked[0] == "5"
        assert masked[-1] == "7"
        assert "*" in masked

    def test_empty_and_nan_pass_through(self):
        assert mask_value("") == ""
        assert mask_value("nan") == "nan"


class TestDetectSensitiveDataByName:
    def test_email_column_name(self):
        s = pd.Series(["not-checked"] * 5)
        result = detect_sensitive_data(s, "user_email", skip_content=True)
        assert result["is_sensitive"] is True
        assert result["category"] == "PII"
        assert result["type"] == "email"
        assert "column_name" in result["detected_by"]

    def test_unrelated_column_name_not_flagged(self):
        s = pd.Series(["x"] * 5)
        result = detect_sensitive_data(s, "widget_count", skip_content=True)
        assert result["is_sensitive"] is False

    def test_generic_name_substring_not_flagged(self):
        # "database" contains "data" but must not match unrelated PII tokens;
        # specifically a bare "name" pattern is deliberately excluded.
        s = pd.Series(["x"] * 5)
        result = detect_sensitive_data(s, "file_name", skip_content=True)
        assert result["is_sensitive"] is False

    def test_diagnosis_maps_to_phi_group(self):
        s = pd.Series(["x"] * 5)
        result = detect_sensitive_data(s, "diagnosis_code", skip_content=True)
        assert result["category"] == "PHI"


class TestDetectSensitiveDataByContent:
    def test_email_content_detected_without_name_hint(self):
        s = pd.Series(["a@example.com", "b@example.com", "c@example.com"] * 10)
        result = detect_sensitive_data(s, "col_a", skip_content=False)
        assert result["is_sensitive"] is True
        assert result["type"] == "email"
        assert "content_pattern" in result["detected_by"]

    def test_credit_card_requires_luhn_pass(self):
        # Digit-shaped but fails Luhn -> should NOT be flagged as credit_card.
        s = pd.Series(["1234567890123456"] * 10)
        result = detect_sensitive_data(s, "col_b", skip_content=False)
        assert result["type"] != "credit_card"

    def test_valid_credit_card_numbers_detected(self):
        s = pd.Series(["4532015112830366"] * 10)
        result = detect_sensitive_data(s, "col_c", skip_content=False)
        assert result["type"] == "credit_card"
        assert result["category"] == "PCI"

    def test_skip_content_ignores_value_shape(self):
        s = pd.Series(["a@example.com"] * 10)
        result = detect_sensitive_data(s, "unrelated_name", skip_content=True)
        assert result["is_sensitive"] is False

    def test_non_matching_content_not_flagged(self):
        s = pd.Series(["apple", "banana", "cherry"] * 10)
        result = detect_sensitive_data(s, "fruit", skip_content=False)
        assert result["is_sensitive"] is False


class TestConfidenceCombination:
    def test_name_and_content_agreement_raises_confidence(self):
        s = pd.Series(["a@example.com"] * 10)
        name_only = detect_sensitive_data(pd.Series(["x"] * 10), "email", skip_content=True)
        both = detect_sensitive_data(s, "email", skip_content=False)
        assert both["confidence"] >= name_only["confidence"]

    def test_confidence_capped_at_0_99(self):
        s = pd.Series(["a@example.com"] * 10)
        result = detect_sensitive_data(s, "email_address", skip_content=False)
        assert result["confidence"] <= 0.99


class TestPlainLanguage:
    def test_labels_and_reasons_explain_a_flag(self):
        s = detect_sensitive_data(pd.Series(["ann@x.com"] * 9 + ["n/a"]), "contact_email")
        assert (s["category_label"], s["type_label"]) == ("Personal data", "email address")
        assert s["reasons"] == ["Its name suggests it holds an email address.",
                                "90% of 10 sampled values have the format of an email address."]

    def test_reasons_mention_the_checksum_and_never_quote_values(self):
        s = detect_sensitive_data(pd.Series(["4111111111111111"] * 10), "ref")
        assert s["category_label"] == "Payment data"
        assert s["reasons"] == ["100% of 10 sampled values have the format of a credit card number "
                                "and pass its checksum."]
        assert not any("4111" in r for r in s["reasons"])

    def test_not_sensitive_has_empty_explanations(self):
        s = detect_sensitive_data(pd.Series(["a", "b"]), "colour")
        assert s["reasons"] == [] and s["category_label"] is None

    def test_ip_address_is_not_mistaken_for_a_postal_address(self):
        s = detect_sensitive_data(pd.Series([], dtype=object), "ip_address", skip_content=True)
        assert s["type"] == "ip_address" and s["type_label"] == "IP address"
        assert detect_sensitive_data(pd.Series([], dtype=object), "shipping_address", skip_content=True)["type"] == "address"


def test_alert_and_rule_use_plain_language():
    from datascope import DataProfiler
    df = pd.DataFrame({"email": [f"user{i}@example.com" for i in range(50)]})
    result = DataProfiler().profile(df)
    [alert] = [a for a in result["overview"]["alerts"] if a["severity"] == "sensitive"]
    assert alert["message"] == "Looks like personal data (email address): review who can access it."
    rule = next(r for r in result["columns"][0]["quality_rules"] if r["type"] == "access_control")
    assert rule["description"].startswith("Looks like personal data (email address):")


class TestPartialAndEmbedded:
    """Even a column that is only partly personal data gets flagged."""

    def test_a_few_percent_of_emails_is_enough(self):
        values = ["unknown"] * 97 + ["a@x.com", "b@y.org", "c@z.net"]
        s = detect_sensitive_data(pd.Series(values), "c1")
        assert s["is_sensitive"] and s["type"] == "email"
        assert s["reasons"] == ["3% of 100 sampled values have the format of an email address."]

    def test_threshold_is_respected(self):
        values = ["unknown"] * 97 + ["a@x.com", "b@y.org", "c@z.net"]
        assert not detect_sensitive_data(pd.Series(values), "c1", min_match_rate=0.05)["is_sensitive"]

    def test_emails_and_dashed_ids_inside_free_text(self):
        notes = ["all good"] * 8 + ["please email ann.lee@corp.co.uk tomorrow", "SSN on file: 123-45-6789."]
        s = detect_sensitive_data(pd.Series(notes), "c1")
        assert s["is_sensitive"] and s["type"] in ("email", "national_id")
        assert "contain" in s["reasons"][0]
        # numbers in prose that aren't dashed IDs or emails don't count
        prose = ["order 123456789 shipped", "call back at 3pm", "version 2.1.0"] * 10
        assert not detect_sensitive_data(pd.Series(prose), "c1")["is_sensitive"]

    def test_dashed_ssn_is_labelled_national_id_not_phone(self):
        values = ["none"] * 99 + ["123-45-6789"]
        assert detect_sensitive_data(pd.Series(values), "c1")["type"] == "national_id"

    def test_iban_shaped_codes_need_a_valid_checksum(self):
        codes = [f"AB{10 + i % 80}CDEFGH{i:08d}" for i in range(100)]  # IBAN-shaped, checksums fail
        assert not detect_sensitive_data(pd.Series(codes), "c1")["is_sensitive"]
        ibans = ["GB82WEST12345698765432", "DE89370400440532013000", "FR1420041010050500013M02606"] * 10
        s = detect_sensitive_data(pd.Series(ibans), "c1")
        assert s["type"] == "bank_account" and s["reasons"][0].endswith("and pass its checksum.")


def test_every_flagged_column_alerts_by_default_and_the_bar_is_a_setting():
    from datascope import DataProfiler
    df = pd.DataFrame({"full_name": [f"Person {i}" for i in range(40)],                       # name only: 0.55
                       "c1": ["unknown"] * 38 + ["a@x.com", "b@y.org"]})                       # 5% emails
    alerted = lambda **kw: sorted(a["column"] for a in DataProfiler(**kw).profile(df)["overview"]["alerts"]
                                  if a["severity"] == "sensitive")
    assert alerted() == ["c1", "full_name"]
    assert alerted(sensitive_alert_min_confidence=0.5) == ["full_name"]
    assert alerted(sensitive_min_match_pct=10) == ["full_name"]


def test_dependency_exceptions_are_masked_for_personal_data_columns():
    from datascope import DataProfiler
    n = 200
    full_name = [f"Leader Number{i % 5}" for i in range(n)]
    team = [f"team_{i % 5}" for i in range(n)]
    team[7] = "team_4"  # one exception to full_name -> team (row 7 is Leader Number2)
    deps = DataProfiler().profile(pd.DataFrame({"full_name": full_name, "team": team}))["column_dependencies"]
    dep = next(d for d in deps if (d["determinant"], d["dependent"]) == ("full_name", "team"))
    [example] = dep["violation_examples"]
    assert example["determinant_value"] != "Leader Number2" and example["determinant_value"].startswith("L")
    assert example["dependent_value"] == "team_4"  # not a personal-data column: shown as is
