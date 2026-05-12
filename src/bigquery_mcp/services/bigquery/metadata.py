"""Metadata service: list datasets, list tables, get table schema, describe table, get column values."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseBigQueryService

logger = logging.getLogger(__name__)


class MetadataService(BaseBigQueryService):
    """Service for dataset/table metadata operations with multi-connection routing."""

    def list_datasets(self, connection: Optional[str] = None) -> Dict[str, Any]:
        """List all accessible datasets for a connection (or default)."""
        logger.info("[list_datasets] connection=%s", connection or "default")
        conn_name = self._resolve_connection_name(connection=connection)
        client = self._get_client(connection=conn_name)
        datasets = client.list_datasets()

        # Apply per-connection dataset filter
        from bigquery_mcp.utils.config_parser import config_parser
        conn_config = config_parser.get_connection_config(conn_name) or {}
        allowed = conn_config.get("datasets", [])
        if allowed:
            datasets = [ds for ds in datasets if ds["dataset_id"] in allowed]

        logger.info("[list_datasets] Found %d datasets on '%s'", len(datasets), conn_name)
        return {"status": "ok", "connection": conn_name, "datasets": datasets, "count": len(datasets)}

    def list_tables(self, dataset: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """List all tables in a dataset (auto-routes to correct connection)."""
        logger.info("[list_tables] dataset='%s', connection=%s", dataset, connection or "auto")
        dataset = self._validate_dataset_name(dataset)

        conn_name = connection or self._resolve_connection_name(table_name=f"{dataset}.placeholder")
        self._check_datasets_filter(dataset, connection=conn_name)
        client = self._get_client(connection=conn_name)

        tables = client.list_tables(dataset)
        logger.info("[list_tables] Found %d tables in '%s' (via '%s')", len(tables), dataset, conn_name)
        return {"status": "ok", "connection": conn_name, "dataset": dataset, "tables": tables, "count": len(tables)}

    def get_table_schema(self, table_name: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """Get column schema and basic metadata for a table."""
        logger.info("[get_table_schema] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        self._check_table_accessible(table_name)
        client = self._get_client(connection=connection, table_name=table_name)

        schema = client.get_table_schema(table_name)
        info = client.get_table(table_name)

        result: Dict[str, Any] = {
            "status": "ok",
            "table": table_name,
            "connection": self._resolve_connection_name(connection=connection, table_name=table_name),
            "columns": schema,
            "column_count": len(schema),
        }
        if info.get("time_partitioning"):
            result["time_partitioning"] = info["time_partitioning"]
        if info.get("clustering_fields"):
            result["clustering_fields"] = info["clustering_fields"]
        if info.get("num_rows") is not None:
            result["num_rows"] = info["num_rows"]

        logger.info("[get_table_schema] Retrieved %d columns for '%s'", len(schema), table_name)
        return result

    def describe_table(self, table_name: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """Get DDL (CREATE TABLE statement) for a table."""
        logger.info("[describe_table] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        self._check_table_accessible(table_name)
        client = self._get_client(connection=connection, table_name=table_name)

        ddl = client.get_ddl(table_name)
        logger.info("[describe_table] Retrieved DDL for '%s'", table_name)
        return {"status": "ok", "table": table_name, "ddl": ddl}

    def get_column_values(
        self,
        table_name: str,
        column: str,
        limit: int = 50,
        connection: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get distinct values for a column (live query to BigQuery).

        Args:
            table_name: Table containing the column.
            column: Column name to get values for.
            limit: Max number of distinct values.
            connection: Optional explicit connection name.
        """
        logger.info("[get_column_values] table='%s', column='%s', limit=%d", table_name, column, limit)
        table_name = self._validate_table_name(table_name)
        self._check_table_accessible(table_name)
        column = self._validate_column_name(column)
        limit = max(1, min(limit, 200))
        client = self._get_client(connection=connection, table_name=table_name)

        values = client.get_distinct_values(table_name, column, limit)
        logger.info("[get_column_values] Found %d values for '%s.%s'", len(values), table_name, column)
        return {
            "status": "ok",
            "table": table_name,
            "column": column,
            "values": values,
            "count": len(values),
        }
