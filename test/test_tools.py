"""Tests for MCP tools layer — thin wrappers over services."""
from unittest.mock import patch, MagicMock

import pytest


class TestMetadataTools:
    """Test metadata tool output formatting."""

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_list_datasets_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import list_datasets

        mock_svc.list_datasets.return_value = {
            "status": "ok",
            "connection": "prod-us",
            "datasets": [
                {"dataset_id": "analytics", "location": "US"},
                {"dataset_id": "sales", "location": "EU"},
            ],
            "count": 2,
        }
        output = list_datasets()
        assert "prod-us" in output
        assert "analytics" in output
        assert "sales" in output
        assert "(2)" in output
        assert "location: US" in output
        assert "location: EU" in output

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_list_datasets_empty(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import list_datasets

        mock_svc.list_datasets.return_value = {
            "status": "ok",
            "connection": "prod-us",
            "datasets": [],
            "count": 0,
        }
        output = list_datasets()
        assert "No datasets" in output

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_list_datasets_error(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import list_datasets

        mock_svc.list_datasets.side_effect = Exception("Connection failed")
        output = list_datasets()
        assert "Error" in output

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_list_tables_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import list_tables

        mock_svc.list_tables.return_value = {
            "status": "ok",
            "connection": "prod-us",
            "dataset": "analytics",
            "tables": [
                {"table_id": "orders", "table_type": "TABLE", "num_rows": 50000},
            ],
            "count": 1,
        }
        output = list_tables("analytics")
        assert "orders" in output
        assert "TABLE" in output
        assert "50,000" in output

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_get_table_schema_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import get_table_schema

        mock_svc.get_table_schema.return_value = {
            "status": "ok",
            "table": "analytics.orders",
            "connection": "prod-us",
            "columns": [
                {"name": "id", "type": "INTEGER", "mode": "REQUIRED"},
                {"name": "email", "type": "STRING", "mode": "NULLABLE"},
            ],
            "column_count": 2,
            "num_rows": 1000,
            "partitioning": {"field": "created_at", "type": "DAY"},
            "clustering_fields": ["region", "status"],
        }
        output = get_table_schema("analytics.orders")
        assert "id: INTEGER" in output
        assert "REQUIRED" in output
        assert "Partitioned by" in output
        assert "Clustered by" in output
        assert "1,000" in output

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_describe_table_returns_ddl(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import describe_table

        mock_svc.describe_table.return_value = {
            "status": "ok",
            "table": "analytics.orders",
            "ddl": "CREATE TABLE `project.analytics.orders` (\n  id INT64\n)",
        }
        output = describe_table("analytics.orders")
        assert "CREATE TABLE" in output

    @patch("bigquery_mcp.tools.bigquery.metadata.bigquery_service")
    def test_get_column_values_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.metadata import get_column_values

        mock_svc.get_column_values.return_value = {
            "status": "ok",
            "table": "analytics.orders",
            "column": "status",
            "values": ["active", "inactive"],
            "count": 2,
        }
        output = get_column_values("analytics.orders", "status")
        assert "active" in output
        assert "inactive" in output


class TestQueryTools:
    """Test query tool output formatting."""

    @patch("bigquery_mcp.tools.bigquery.query.bigquery_service")
    def test_dry_run_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.query import dry_run_query

        mock_svc.dry_run_query.return_value = {
            "status": "ok",
            "valid": True,
            "connection": "prod-us",
            "query": "SELECT * FROM t",
            "estimation": {
                "total_bytes_processed": 1_073_741_824,
                "referenced_tables": [{"dataset_id": "analytics", "table_id": "orders"}],
                "schema": [{"name": "id", "type": "INTEGER"}],
            },
        }
        output = dry_run_query("SELECT * FROM t")
        assert "valid" in output.lower()
        assert "GiB" in output
        assert "analytics.orders" in output
        assert "id (INTEGER)" in output

    @patch("bigquery_mcp.tools.bigquery.query.bigquery_service")
    def test_dry_run_mib(self, mock_svc):
        from bigquery_mcp.tools.bigquery.query import dry_run_query

        mock_svc.dry_run_query.return_value = {
            "status": "ok",
            "valid": True,
            "connection": "prod-us",
            "query": "SELECT 1",
            "estimation": {"total_bytes_processed": 5_242_880},
        }
        output = dry_run_query("SELECT 1")
        assert "MiB" in output

    @patch("bigquery_mcp.tools.bigquery.query.bigquery_service")
    def test_execute_query_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.query import execute_query

        mock_svc.execute_query.return_value = {
            "status": "ok",
            "connection": "prod-us",
            "rows": [{"id": 1, "name": "Alice"}],
            "count": 1,
            "query": "SELECT * FROM t LIMIT 100",
            "modifications": ["Added LIMIT 100"],
            "masked_fields": ["email"],
        }
        output = execute_query("SELECT * FROM t")
        assert "1 rows returned" in output
        assert "Modifications" in output
        assert "PII masked" in output
        assert '"Alice"' in output

    @patch("bigquery_mcp.tools.bigquery.query.bigquery_service")
    def test_execute_query_error_with_stage(self, mock_svc):
        from bigquery_mcp.tools.bigquery.query import execute_query

        mock_svc.execute_query.return_value = {
            "status": "error",
            "message": "Rate limit exceeded",
            "stage": "rate_limit",
        }
        output = execute_query("SELECT * FROM t")
        assert "Error" in output
        assert "rate_limit" in output

    @patch("bigquery_mcp.tools.bigquery.query.bigquery_service")
    def test_explain_query_error_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.query import explain_query_error

        mock_svc.explain_query_error.return_value = {
            "status": "ok",
            "error_message": "Table not found",
            "query": "SELECT * FROM bad.table",
            "suggestions": ["Check table name", "Use list_tables"],
        }
        output = explain_query_error("Table not found", "SELECT * FROM bad.table")
        assert "Suggestions" in output
        assert "1." in output
        assert "2." in output

    @patch("bigquery_mcp.tools.bigquery.query.bigquery_service")
    def test_get_status_formatted(self, mock_svc):
        from bigquery_mcp.tools.bigquery.query import get_status

        mock_svc.get_status.return_value = {
            "status": "ok",
            "default_connection": "prod-us",
            "connections": {
                "prod-us": {"status": "connected", "project": "my-prod"},
            },
            "guardrails": {
                "read_only": True,
                "default_limit": 100,
                "max_limit": 1000,
                "max_bytes_billed": 10_737_418_240,
                "max_query_length": 10_000,
                "forbid_cross_connection": False,
                "rate_limit": {
                    "calls_used": 5,
                    "remaining": 95,
                    "limit": 100,
                    "window_seconds": 3600,
                },
            },
            "blocked_tables": ["internal.*"],
            "pii_rules_count": 2,
        }
        output = get_status()
        assert "prod-us" in output
        assert "connected" in output
        assert "Read-only: True" in output
        assert "GiB" in output
        assert "internal.*" in output
        assert "PII rules: 2" in output
