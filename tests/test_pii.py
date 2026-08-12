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
