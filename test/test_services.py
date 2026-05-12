"""Tests for BigQuery services — MetadataService and QueryService."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_deps():
    """Mock config_parser and connection_manager for service tests."""
    with patch("bigquery_mcp.services.bigquery.base.connection_manager") as mock_cm, \
         patch("bigquery_mcp.utils.config_parser.ConfigParser._instance", None), \
         patch("bigquery_mcp.utils.config_parser.ConfigParser._config", None):

        mock_client = MagicMock()
        mock_cm.get_client.return_value = mock_client
        mock_cm.get_default_client.return_value = mock_client

        yield {
            "connection_manager": mock_cm,
            "client": mock_client,
        }


class TestMetadataService:
    """Test MetadataService methods."""

    def test_list_datasets(self, mock_deps):
        from bigquery_mcp.services.bigquery.metadata import MetadataService

        mock_deps["client"].list_datasets.return_value = [
            {"dataset_id": "analytics", "location": "US"},
            {"dataset_id": "sales", "location": "US"},
        ]

        svc = MetadataService()
        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {"datasets": []}
            with patch.object(svc, "_resolve_connection_name", return_value="prod-us"):
                with patch.object(svc, "_get_client", return_value=mock_deps["client"]):
                    result = svc.list_datasets(connection="prod-us")

        assert result["status"] == "ok"
        assert result["count"] == 2

    def test_list_tables(self, mock_deps):
        from bigquery_mcp.services.bigquery.metadata import MetadataService

        mock_deps["client"].list_tables.return_value = [
            {"table_id": "orders", "table_type": "TABLE", "num_rows": 1000},
        ]

        svc = MetadataService()
        with patch.object(svc, "_validate_dataset_name", return_value="analytics"), \
             patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_check_datasets_filter"), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.list_tables("analytics")

        assert result["status"] == "ok"
        assert result["count"] == 1
        assert result["tables"][0]["table_id"] == "orders"

    def test_get_table_schema(self, mock_deps):
        from bigquery_mcp.services.bigquery.metadata import MetadataService

        mock_deps["client"].get_table_schema.return_value = [
            {"name": "id", "type": "INTEGER", "mode": "REQUIRED"},
            {"name": "name", "type": "STRING", "mode": "NULLABLE"},
        ]
        mock_deps["client"].get_table.return_value = {
            "num_rows": 500,
            "partitioning_type": "DAY",
            "partitioning_field": "created_at",
            "clustering_fields": None,
        }

        svc = MetadataService()
        with patch.object(svc, "_validate_table_name", return_value="analytics.orders"), \
             patch.object(svc, "_check_table_accessible"), \
             patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.get_table_schema("analytics.orders")

        assert result["status"] == "ok"
        assert result["column_count"] == 2
        assert result["num_rows"] == 500

    def test_describe_table(self, mock_deps):
        from bigquery_mcp.services.bigquery.metadata import MetadataService

        mock_deps["client"].get_ddl.return_value = "CREATE TABLE `project.dataset.table` (\n  id INT64\n)"

        svc = MetadataService()
        with patch.object(svc, "_validate_table_name", return_value="analytics.orders"), \
             patch.object(svc, "_check_table_accessible"), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.describe_table("analytics.orders")

        assert result["status"] == "ok"
        assert "CREATE TABLE" in result["ddl"]

    def test_get_column_values(self, mock_deps):
        from bigquery_mcp.services.bigquery.metadata import MetadataService

        mock_deps["client"].get_distinct_values.return_value = ["active", "inactive", "pending"]

        svc = MetadataService()
        with patch.object(svc, "_validate_table_name", return_value="analytics.orders"), \
             patch.object(svc, "_check_table_accessible"), \
             patch.object(svc, "_validate_column_name", return_value="status"), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.get_column_values("analytics.orders", "status", limit=50)

        assert result["status"] == "ok"
        assert result["count"] == 3
        assert "active" in result["values"]


class TestQueryService:
    """Test QueryService methods."""

    def test_execute_query_success(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService
        from bigquery_mcp.services.bigquery.guardrails import GuardrailsPipeline

        mock_deps["client"].execute_query.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

        pipeline = GuardrailsPipeline(
            {"default_limit": 100, "max_limit": 1000, "max_query_length": 10_000,
             "rate_limit": {"max_calls": 100, "window_seconds": 3600}},
            [],
        )

        svc = QueryService()
        with patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_guardrails", return_value={
                 "read_only": True, "max_bytes_billed": 10_000_000,
                 "default_limit": 100, "max_limit": 1000,
                 "max_query_length": 10_000,
                 "rate_limit": {"max_calls": 100, "window_seconds": 3600},
             }), \
             patch.object(svc, "_get_pipeline", return_value=pipeline), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.execute_query("SELECT id, name FROM analytics.orders")

        assert result["status"] == "ok"
        assert result["count"] == 2
        assert result["connection"] == "prod-us"

    def test_execute_query_empty(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        svc = QueryService()
        result = svc.execute_query("")
        assert result["status"] == "error"
        assert "empty" in result["message"].lower()

    def test_execute_query_read_only_blocks_dml(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        svc = QueryService()
        with patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_guardrails", return_value={"read_only": True}):
            result = svc.execute_query("INSERT INTO t VALUES (1)")

        assert result["status"] == "error"
        assert "read-only" in result["message"].lower() or "SELECT" in result["message"]

    def test_execute_query_allows_explain(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService
        from bigquery_mcp.services.bigquery.guardrails import GuardrailsPipeline

        mock_deps["client"].execute_query.return_value = [{"plan": "scan"}]

        pipeline = GuardrailsPipeline(
            {"default_limit": 100, "max_limit": 1000, "max_query_length": 10_000,
             "rate_limit": {"max_calls": 100, "window_seconds": 3600}},
            [],
        )

        svc = QueryService()
        with patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_guardrails", return_value={
                 "read_only": True, "max_bytes_billed": 10_000_000,
                 "query_timeout_seconds": 300,
             }), \
             patch.object(svc, "_get_pipeline", return_value=pipeline), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.execute_query("EXPLAIN SELECT 1")

        assert result["status"] == "ok"

    def test_dry_run_query_success(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        mock_deps["client"].dry_run.return_value = {
            "total_bytes_processed": 1_000_000,
            "referenced_tables": [{"dataset_id": "analytics", "table_id": "orders"}],
        }

        svc = QueryService()
        with patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_guardrails", return_value={
                 "read_only": True, "max_bytes_billed": 10_000_000,
                 "max_query_length": 10_000,
             }), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.dry_run_query("SELECT * FROM analytics.orders")

        assert result["status"] == "ok"
        assert result["valid"] is True
        assert result["estimation"]["total_bytes_processed"] == 1_000_000

    def test_dry_run_query_blocks_dml(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        svc = QueryService()
        with patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_guardrails", return_value={"read_only": True}):
            result = svc.dry_run_query("DELETE FROM t WHERE id=1")

        assert result["status"] == "error"

    def test_dry_run_allows_explain(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        mock_deps["client"].dry_run.return_value = {
            "total_bytes_processed": 0,
            "referenced_tables": [],
        }

        svc = QueryService()
        with patch.object(svc, "_resolve_connection_name", return_value="prod-us"), \
             patch.object(svc, "_get_guardrails", return_value={
                 "read_only": True, "max_bytes_billed": 10_000_000,
                 "max_query_length": 10_000,
             }), \
             patch.object(svc, "_get_client", return_value=mock_deps["client"]):
            result = svc.dry_run_query("EXPLAIN SELECT * FROM t")

        assert result["status"] == "ok"

    def test_explain_query_error_table_not_found(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        svc = QueryService()
        result = svc.explain_query_error(
            "Not found: Table project:dataset.table",
            "SELECT * FROM dataset.table",
        )
        assert result["status"] == "ok"
        assert any("table" in s.lower() for s in result["suggestions"])

    def test_explain_query_error_syntax(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        svc = QueryService()
        result = svc.explain_query_error(
            "Syntax error at position 10",
            "SELEC * FROM table",
        )
        assert result["status"] == "ok"
        assert any("syntax" in s.lower() for s in result["suggestions"])

    def test_explain_query_error_empty_inputs(self, mock_deps):
        from bigquery_mcp.services.bigquery.query import QueryService

        svc = QueryService()
        result = svc.explain_query_error("", "SELECT 1")
        assert result["status"] == "error"


class TestQueryClientTimeout:
    """Test that timeout is correctly passed to .result() not .query()."""

    def test_execute_query_passes_timeout_to_result(self):
        """Timeout must be on query_job.result(), not client.query()."""
        from bigquery_mcp.clients.bigquery.query import QueryClient

        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_bq_client.query.return_value = mock_query_job
        mock_query_job.result.return_value = iter([])

        client = QueryClient.__new__(QueryClient)
        client._client = mock_bq_client

        client.execute_query("SELECT 1", timeout=42.0)

        # timeout should NOT be passed to .query()
        call_kwargs = mock_bq_client.query.call_args
        assert "timeout" not in call_kwargs.kwargs or call_kwargs.kwargs.get("timeout") is None

        # timeout SHOULD be passed to .result()
        mock_query_job.result.assert_called_once_with(timeout=42.0)

    def test_execute_query_no_timeout_passes_none(self):
        """When timeout is None, result() still gets None (no infinite wait difference)."""
        from bigquery_mcp.clients.bigquery.query import QueryClient

        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_bq_client.query.return_value = mock_query_job
        mock_query_job.result.return_value = iter([])

        client = QueryClient.__new__(QueryClient)
        client._client = mock_bq_client

        client.execute_query("SELECT 1", timeout=None)
        mock_query_job.result.assert_called_once_with(timeout=None)

    def test_get_distinct_values_has_timeout(self):
        """get_distinct_values passes timeout to .result()."""
        from bigquery_mcp.clients.bigquery.query import QueryClient

        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_bq_client.query.return_value = mock_query_job
        mock_query_job.result.return_value = iter([])

        client = QueryClient.__new__(QueryClient)
        client._client = mock_bq_client

        client.get_distinct_values("project.dataset.table", "col")
        mock_query_job.result.assert_called_once_with(timeout=60.0)

    def test_get_distinct_values_custom_timeout(self):
        """get_distinct_values accepts custom timeout."""
        from bigquery_mcp.clients.bigquery.query import QueryClient

        mock_bq_client = MagicMock()
        mock_query_job = MagicMock()
        mock_bq_client.query.return_value = mock_query_job
        mock_query_job.result.return_value = iter([])

        client = QueryClient.__new__(QueryClient)
        client._client = mock_bq_client

        client.get_distinct_values("project.dataset.table", "col", timeout=120.0)
        mock_query_job.result.assert_called_once_with(timeout=120.0)


class TestTableNameValidation:
    """Test _validate_table_name blocks SQL injection via identifiers."""

    def test_valid_two_part(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        assert svc._validate_table_name("dataset.table") == "dataset.table"

    def test_valid_three_part(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        assert svc._validate_table_name("project.dataset.table") == "project.dataset.table"

    def test_rejects_backtick_injection(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_table_name("dataset.`table`")

    def test_rejects_semicolon_injection(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_table_name("dataset.table; DROP TABLE x")

    def test_rejects_space_in_name(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_table_name("dataset.my table")

    def test_rejects_empty(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_table_name("")

    def test_rejects_single_part(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_table_name("table_only")

    def test_allows_hyphens_and_underscores(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        assert svc._validate_table_name("my-project.my_dataset.my-table") == "my-project.my_dataset.my-table"


class TestColumnNameValidation:
    """Test _validate_column_name blocks injection via column params."""

    def test_valid_column(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        assert svc._validate_column_name("user_id") == "user_id"

    def test_rejects_backtick(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_column_name("`col`")

    def test_rejects_space(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_column_name("col name")

    def test_rejects_semicolon(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_column_name("col;DROP")

    def test_rejects_hyphen(self):
        from bigquery_mcp.services.bigquery.metadata import MetadataService
        svc = MetadataService()
        with pytest.raises(ValueError):
            svc._validate_column_name("col-name")
