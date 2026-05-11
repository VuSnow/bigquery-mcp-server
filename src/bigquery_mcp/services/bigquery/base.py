"""Base service — shared utilities for all BigQuery service mixins."""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List

from bigquery_mcp.services.connection_manager import connection_manager, ConnectionState
from bigquery_mcp.clients.bigquery import BigQueryClient
from bigquery_mcp.configs import configs

logger = logging.getLogger(__name__)


class BaseBigQueryService:
    """Base service — provides auto-connect, validation, and policy enforcement."""

    def _ensure_connected(self) -> BigQueryClient:
        """Auto-connect if not connected. Returns the active client."""
        if connection_manager.state != ConnectionState.CONNECTED:
            logger.info("[connection] State=%s — initiating auto-connect", connection_manager.state.value)
            connection_manager.connect()
            logger.info("[connection] Auto-connect successful")
        return connection_manager.get_client()

    def _check_read_only(self) -> None:
        """Raise if server is in read-only mode and a write is attempted."""
        if configs.read_only:
            logger.warning("[policy] Write operation blocked — server is in READ_ONLY mode")
            raise PermissionError("Write operations are disabled in read-only mode.")

    def _validate_table_name(self, table_name: str) -> str:
        """Validate and sanitize table name format.

        Accepts: dataset.table or project.dataset.table
        Returns: sanitized table name.
        Raises: ValueError if invalid.
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

    def _check_datasets_filter(self, dataset: str) -> None:
        """Raise if dataset is not in the configured filter (when filter is set)."""
        if not configs.datasets_filter:
            return
        allowed = [d.strip() for d in configs.datasets_filter.split(",") if d.strip()]
        if allowed and dataset not in allowed:
            raise PermissionError(
                f"Dataset '{dataset}' is not in the allowed list. "
                f"Allowed: {', '.join(allowed)}"
            )
