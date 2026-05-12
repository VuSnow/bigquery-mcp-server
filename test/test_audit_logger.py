"""Tests for AuditLogger — structured audit logging."""
import pytest

from bigquery_mcp.services.bigquery.guardrails.audit_logger import AuditLogger


class TestAuditLoggerQuery:
    """Test query execution logging."""

    def test_log_query_ok(self):
        record = AuditLogger.log_query(
            query="SELECT * FROM table",
            connection="prod-us",
            status="ok",
            rows_returned=10,
        )
        assert record["event"] == "query_execution"
        assert record["connection"] == "prod-us"
        assert record["status"] == "ok"
        assert record["rows_returned"] == 10
        assert record["query_length"] == len("SELECT * FROM table")
        assert "timestamp" in record

    def test_log_query_with_optional_fields(self):
        record = AuditLogger.log_query(
            query="SELECT * FROM table",
            connection="prod-us",
            status="ok",
            rows_returned=5,
            bytes_processed=1024,
            modifications=["Added LIMIT 100"],
            masked_fields=["email"],
        )
        assert record["bytes_processed"] == 1024
        assert record["modifications"] == ["Added LIMIT 100"]
        assert record["masked_fields"] == ["email"]

    def test_log_query_error(self):
        record = AuditLogger.log_query(
            query="SELECT * FROM table",
            connection="prod-us",
            status="error",
            error="Table not found",
        )
        assert record["status"] == "error"
        assert record["error"] == "Table not found"

    def test_error_truncated(self):
        long_error = "x" * 500
        record = AuditLogger.log_query(
            query="SELECT 1",
            connection="prod-us",
            status="error",
            error=long_error,
        )
        assert len(record["error"]) == 200


class TestAuditLoggerBlocked:
    """Test blocked query logging."""

    def test_log_blocked(self):
        record = AuditLogger.log_blocked(
            query="DROP TABLE foo",
            connection="prod-us",
            reason="Forbidden operation: 'drop'",
            stage="security_validator",
        )
        assert record["event"] == "query_blocked"
        assert record["connection"] == "prod-us"
        assert record["reason"] == "Forbidden operation: 'drop'"
        assert record["stage"] == "security_validator"
        assert "timestamp" in record

    def test_log_blocked_rate_limit(self):
        record = AuditLogger.log_blocked(
            query="SELECT * FROM table",
            connection="prod-us",
            reason="Rate limit exceeded",
            stage="rate_limit",
        )
        assert record["stage"] == "rate_limit"
