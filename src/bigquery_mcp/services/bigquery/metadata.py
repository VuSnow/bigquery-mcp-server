"""Metadata service: list datasets, list tables, get table info, get table schema, describe table."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseBigQueryService

logger = logging.getLogger(__name__)


class MetadataService(BaseBigQueryService):
    """Service for dataset/table metadata operations."""

    def list_datasets(self) -> Dict[str, Any]:
        """List all accessible datasets."""
        logger.info("[list_datasets] Fetching datasets")
        client = self._ensure_connected()
        datasets = client.list_datasets()

        # Apply filter if configured
        from bigquery_mcp.configs import configs
        if configs.datasets_filter:
            allowed = [d.strip() for d in configs.datasets_filter.split(",") if d.strip()]
            if allowed:
                datasets = [ds for ds in datasets if ds["dataset_id"] in allowed]

        logger.info("[list_datasets] Found %d datasets", len(datasets))
        return {"status": "ok", "datasets": datasets, "count": len(datasets)}

    def list_tables(self, dataset: str) -> Dict[str, Any]:
        """List all tables in a dataset."""
        logger.info("[list_tables] dataset='%s'", dataset)
        dataset = self._validate_dataset_name(dataset)
        self._check_datasets_filter(dataset)
        client = self._ensure_connected()

        tables = client.list_tables(dataset)
        logger.info("[list_tables] Found %d tables in '%s'", len(tables), dataset)
        return {"status": "ok", "dataset": dataset, "tables": tables, "count": len(tables)}

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get detailed metadata for a table."""
        logger.info("[get_table_info] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        client = self._ensure_connected()

        info = client.get_table(table_name)
        logger.info("[get_table_info] Retrieved info for '%s'", table_name)
        return {"status": "ok", "table": info}

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Get column schema for a table."""
        logger.info("[get_table_schema] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        client = self._ensure_connected()

        schema = client.get_table_schema(table_name)
        logger.info("[get_table_schema] Retrieved %d columns for '%s'", len(schema), table_name)
        return {"status": "ok", "table": table_name, "columns": schema, "count": len(schema)}

    def describe_table(self, table_name: str) -> Dict[str, Any]:
        """Get DDL (CREATE TABLE statement) for a table."""
        logger.info("[describe_table] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        client = self._ensure_connected()

        ddl = client.get_ddl(table_name)
        logger.info("[describe_table] Retrieved DDL for '%s'", table_name)
        return {"status": "ok", "table": table_name, "ddl": ddl}
