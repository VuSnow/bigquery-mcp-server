"""Tests for PIIMasker — hash and redact PII columns."""
import hashlib

import pytest

from bigquery_mcp.services.bigquery.guardrails.pii_masker import PIIMasker


class TestPIIMaskerHash:
    """Test hash masking method."""

    def test_hash_email(self):
        masker = PIIMasker([{"column": "email", "method": "hash"}])
        rows = [{"email": "user@example.com", "name": "Alice"}]
        result = masker.mask_rows(rows)

        expected_hash = hashlib.sha256("user@example.com".encode()).hexdigest()[:16]
        assert result["rows"][0]["email"] == expected_hash
        assert result["rows"][0]["name"] == "Alice"  # untouched
        assert "email" in result["masked_fields"]
        assert result["modifications"] == 1

    def test_hash_deterministic(self):
        masker = PIIMasker([{"column": "email", "method": "hash"}])
        rows1 = [{"email": "user@example.com"}]
        rows2 = [{"email": "user@example.com"}]
        r1 = masker.mask_rows(rows1)
        r2 = masker.mask_rows(rows2)
        assert r1["rows"][0]["email"] == r2["rows"][0]["email"]


class TestPIIMaskerRedact:
    """Test redact masking method."""

    def test_redact_phone(self):
        masker = PIIMasker([{"column": "phone_number", "method": "redact"}])
        rows = [{"phone_number": "+1234567890", "id": 1}]
        result = masker.mask_rows(rows)

        assert result["rows"][0]["phone_number"] == "***REDACTED***"
        assert result["rows"][0]["id"] == 1
        assert "phone_number" in result["masked_fields"]

    def test_unknown_method_fallback(self):
        masker = PIIMasker([{"column": "ssn", "method": "unknown_method"}])
        rows = [{"ssn": "123-45-6789"}]
        result = masker.mask_rows(rows)
        assert result["rows"][0]["ssn"] == "***MASKED***"


class TestPIIMaskerMultipleRules:
    """Test multiple PII rules applied together."""

    def test_multiple_columns(self):
        masker = PIIMasker([
            {"column": "email", "method": "hash"},
            {"column": "phone", "method": "redact"},
        ])
        rows = [
            {"email": "a@b.com", "phone": "123", "name": "Alice"},
            {"email": "c@d.com", "phone": "456", "name": "Bob"},
        ]
        result = masker.mask_rows(rows)

        assert result["modifications"] == 4  # 2 rows × 2 fields
        assert set(result["masked_fields"]) == {"email", "phone"}
        assert result["rows"][0]["name"] == "Alice"
        assert result["rows"][1]["name"] == "Bob"


class TestPIIMaskerEdgeCases:
    """Test edge cases."""

    def test_empty_rows(self):
        masker = PIIMasker([{"column": "email", "method": "hash"}])
        result = masker.mask_rows([])
        assert result["rows"] == []
        assert result["masked_fields"] == []
        assert result["modifications"] == 0

    def test_no_rules(self):
        masker = PIIMasker([])
        rows = [{"email": "a@b.com"}]
        result = masker.mask_rows(rows)
        assert result["rows"][0]["email"] == "a@b.com"
        assert result["modifications"] == 0

    def test_null_value_skipped(self):
        masker = PIIMasker([{"column": "email", "method": "hash"}])
        rows = [{"email": None, "name": "Alice"}]
        result = masker.mask_rows(rows)
        assert result["rows"][0]["email"] is None
        assert result["modifications"] == 0

    def test_column_not_in_row(self):
        masker = PIIMasker([{"column": "email", "method": "hash"}])
        rows = [{"name": "Alice", "id": 1}]
        result = masker.mask_rows(rows)
        assert result["rows"][0] == {"name": "Alice", "id": 1}
        assert result["modifications"] == 0

    def test_has_rules_property(self):
        assert PIIMasker([{"column": "email", "method": "hash"}]).has_rules is True
        assert PIIMasker([]).has_rules is False

    def test_invalid_rule_ignored(self):
        masker = PIIMasker([{"bad_key": "value"}, {"column": "email", "method": "hash"}])
        assert len(masker._rules) == 1


class TestPIIMaskerCaseInsensitive:
    """Test case-insensitive column matching."""

    def test_uppercase_column_in_results(self):
        masker = PIIMasker([{"column": "email", "method": "hash"}])
        rows = [{"Email": "test@test.com", "name": "Alice"}]
        result = masker.mask_rows(rows)
        assert result["rows"][0]["Email"] != "test@test.com"
        assert result["masked_fields"] == ["email"]
        assert result["modifications"] == 1

    def test_all_caps_column_in_results(self):
        masker = PIIMasker([{"column": "phone", "method": "redact"}])
        rows = [{"PHONE": "555-1234", "id": 1}]
        result = masker.mask_rows(rows)
        assert result["rows"][0]["PHONE"] == "***REDACTED***"
        assert result["rows"][0]["id"] == 1

    def test_mixed_case_rule_and_column(self):
        masker = PIIMasker([{"column": "Email_Address", "method": "hash"}])
        rows = [{"email_address": "user@test.com"}]
        result = masker.mask_rows(rows)
        assert result["rows"][0]["email_address"] != "user@test.com"
        assert result["modifications"] == 1

    def test_preserves_original_column_key(self):
        """Masked output should keep the original column key casing."""
        masker = PIIMasker([{"column": "email", "method": "redact"}])
        rows = [{"EMAIL": "x@y.com"}]
        result = masker.mask_rows(rows)
        assert "EMAIL" in result["rows"][0]
        assert result["rows"][0]["EMAIL"] == "***REDACTED***"
