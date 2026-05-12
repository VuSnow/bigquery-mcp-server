"""Tests for GuardrailsPipeline — end-to-end orchestration."""
import pytest

from bigquery_mcp.services.bigquery.guardrails import GuardrailsPipeline


@pytest.fixture
def pipeline():
    """Create a pipeline with standard config."""
    guardrails_config = {
        "default_limit": 100,
        "max_limit": 1000,
        "max_query_length": 10_000,
        "rate_limit": {
            "max_calls": 10,
            "window_seconds": 3600,
        },
    }
    pii_rules = [
        {"column": "email", "method": "hash"},
        {"column": "phone", "method": "redact"},
    ]
    return GuardrailsPipeline(guardrails_config, pii_rules)


class TestPipelinePreExecute:
    """Test pre-execution pipeline."""

    def test_valid_query_allowed(self, pipeline):
        result = pipeline.pre_execute("SELECT * FROM dataset.table", "prod-us")
        assert result["allowed"] is True
        assert "LIMIT 100" in result["query"]
        assert "Added LIMIT" in result["modifications"][0]

    def test_preserves_existing_limit(self, pipeline):
        result = pipeline.pre_execute(
            "SELECT * FROM dataset.table LIMIT 50", "prod-us"
        )
        assert result["allowed"] is True
        assert "LIMIT 50" in result["query"]
        assert len(result["modifications"]) == 0

    def test_caps_excessive_limit(self, pipeline):
        result = pipeline.pre_execute(
            "SELECT * FROM dataset.table LIMIT 5000", "prod-us"
        )
        assert result["allowed"] is True
        assert "LIMIT 1000" in result["query"]

    def test_blocks_forbidden_keyword(self, pipeline):
        result = pipeline.pre_execute("DROP TABLE dataset.table", "prod-us")
        assert result["allowed"] is False
        assert result["stage"] == "security_validator"

    def test_blocks_too_long_query(self, pipeline):
        long_query = "SELECT " + "x" * 20_000
        result = pipeline.pre_execute(long_query, "prod-us")
        assert result["allowed"] is False
        assert result["stage"] == "security_validator"

    def test_rate_limit_blocks_after_max(self, pipeline):
        # Use all 10 calls (pre_execute records after passing)
        for _ in range(10):
            result = pipeline.pre_execute("SELECT 1 FROM t", "prod-us")
            assert result["allowed"] is True

        # 11th should be blocked
        result = pipeline.pre_execute("SELECT 1 FROM t", "prod-us")
        assert result["allowed"] is False
        assert result["stage"] == "rate_limit"


class TestPipelinePostExecute:
    """Test post-execution pipeline."""

    def test_masks_pii_fields(self, pipeline):
        rows = [
            {"email": "a@b.com", "phone": "123", "name": "Alice"},
        ]
        result = pipeline.post_execute(rows, "prod-us", "SELECT *", [])
        assert result["rows"][0]["name"] == "Alice"
        assert result["rows"][0]["email"] != "a@b.com"  # hashed
        assert result["rows"][0]["phone"] == "***REDACTED***"
        assert set(result["masked_fields"]) == {"email", "phone"}

    def test_empty_rows(self, pipeline):
        result = pipeline.post_execute([], "prod-us", "SELECT 1", [])
        assert result["rows"] == []
        assert result["masked_fields"] == []

    def test_no_pii_columns(self, pipeline):
        rows = [{"id": 1, "name": "Alice"}]
        result = pipeline.post_execute(rows, "prod-us", "SELECT id, name", [])
        assert result["rows"][0] == {"id": 1, "name": "Alice"}
        assert result["masked_fields"] == []

    def test_audit_record_returned(self, pipeline):
        rows = [{"id": 1}]
        result = pipeline.post_execute(rows, "prod-us", "SELECT id", [])
        assert "audit" in result
        assert result["audit"]["event"] == "query_execution"


class TestPipelineRateLimiterAccess:
    """Test rate limiter property."""

    def test_rate_limiter_accessible(self, pipeline):
        status = pipeline.rate_limiter.get_status()
        assert status["limit"] == 10
        assert status["window_seconds"] == 3600
