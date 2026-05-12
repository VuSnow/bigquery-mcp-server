"""Base service — shared utilities for all BigQuery service mixins."""
from __future__ import annotations

import re
import logging
from typing import Optional

from bigquery_mcp.services.connection_manager import connection_manager
from bigquery_mcp.clients.bigquery import BigQueryClient

logger = logging.getLogger(__name__)


class BaseBigQueryService:
    """Base service — provides connection routing, validation, and access control."""

    def _get_client(self, connection: Optional[str] = None, table_name: Optional[str] = None) -> BigQueryClient:
        """Get the BigQuery client for a connection.

        Resolution order:
        1. Explicit connection name passed
        2. Auto-resolve from table_name
        3. Default connection
        """
        if connection:
            return connection_manager.get_client(connection)

        if table_name:
            from bigquery_mcp.utils.config_parser import config_parser
            resolved = config_parser.resolve_connection_for_table(table_name)
            return connection_manager.get_client(resolved)

        return connection_manager.get_default_client()

    def _resolve_connection_name(self, connection: Optional[str] = None, table_name: Optional[str] = None) -> str:
        """Resolve the connection name (without connecting)."""
        if connection:
            return connection

        from bigquery_mcp.utils.config_parser import config_parser
        if table_name:
            return config_parser.resolve_connection_for_table(table_name)
        return config_parser.get_default_connection_name()

    def _check_table_accessible(self, table_name: str) -> None:
        """Raise if table is blocked."""
        from bigquery_mcp.utils.config_parser import config_parser

        if config_parser.is_table_blocked(table_name):
            raise PermissionError(f"Table '{table_name}' is blocked by configuration.")

    def _check_cross_connection(self, table_names: list[str]) -> None:
        """Raise if tables span multiple connections and forbid_cross_connection is true."""
        from bigquery_mcp.utils.config_parser import config_parser

        guardrails = config_parser.get_guardrails()
        if not guardrails.get("forbid_cross_connection", False):
            return

        connections = set()
        for table in table_names:
            conn = config_parser.resolve_connection_for_table(table)
            connections.add(conn)

        if len(connections) > 1:
            raise PermissionError(
                f"Query spans multiple connections ({connections}). "
                "Cross-connection queries are forbidden by configuration."
            )

    def _get_guardrails(self, connection: Optional[str] = None) -> dict:
        """Get effective guardrails (global + connection override)."""
        from bigquery_mcp.utils.config_parser import config_parser
        return config_parser.get_effective_guardrails(connection)

    def _validate_table_name(self, table_name: str) -> str:
        """Validate and sanitize table name format.

        Accepts: dataset.table or project.dataset.table
        Returns: sanitized table name.
        """
        if not table_name or not table_name.strip():
            raise ValueError("Table name cannot be empty.")

        table_name = table_name.strip()
        parts = table_name.split(".")

        if len(parts) < 2 or len(parts) > 3:
            raise ValueError(
                f"Invalid table name format: '{table_name}'. "
                "Use dataset.table or project.dataset.table."
            )

        for part in parts:
            if not re.match(r"^[a-zA-Z0-9_-]+$", part):
                raise ValueError(f"Invalid characters in table name part: '{part}'.")

        return table_name

    def _validate_dataset_name(self, dataset: str) -> str:
        """Validate dataset name."""
        if not dataset or not dataset.strip():
            raise ValueError("Dataset name cannot be empty.")
        dataset = dataset.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", dataset):
            raise ValueError(f"Invalid dataset name: '{dataset}'.")
        return dataset

    def _validate_column_name(self, column: str) -> str:
        """Validate column name."""
        if not column or not column.strip():
            raise ValueError("Column name cannot be empty.")
        column = column.strip()
        if not re.match(r"^[a-zA-Z0-9_]+$", column):
            raise ValueError(f"Invalid column name: '{column}'.")
        return column

    def _check_datasets_filter(self, dataset: str, connection: Optional[str] = None) -> None:
        """Raise if dataset is not in the connection's datasets filter."""
        from bigquery_mcp.utils.config_parser import config_parser

        conn_name = connection or config_parser.get_default_connection_name()
        conn_config = config_parser.get_connection_config(conn_name)
        if not conn_config:
            return

        allowed = conn_config.get("datasets", [])
        if allowed and dataset not in allowed:
            raise PermissionError(
                f"Dataset '{dataset}' is not in the allowed list for connection '{conn_name}'. "
                f"Allowed: {', '.join(allowed)}"
            )
