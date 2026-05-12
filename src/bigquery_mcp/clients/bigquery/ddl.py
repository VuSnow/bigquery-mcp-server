"""DDL operations: retrieve CREATE TABLE statement."""
from __future__ import annotations

import logging
from typing import Dict, Any

from google.cloud import bigquery

from .base import BaseBigQueryClient

logger = logging.getLogger(__name__)


class DDLClient(BaseBigQueryClient):
    """Mixin for DDL retrieval operations."""

    def get_ddl(self, table_ref: str) -> str:
        """Get the DDL (CREATE TABLE statement) for a table.

        Args:
            table_ref: Fully qualified table name (project.dataset.table or dataset.table).

        Returns:
            DDL string for the table.
        """
        parts = table_ref.rsplit(".", 1)
        dataset_ref = parts[0]
        table_name = parts[1]

        query = (
            f"SELECT ddl FROM `{dataset_ref}`.INFORMATION_SCHEMA.TABLES "
            "WHERE table_name = @table_name"
        )
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("table_name", "STRING", table_name),
            ]
        )
        result = self._client.query(query, job_config=job_config).result()
        rows = list(result)
        if not rows:
            raise ValueError(f"Table not found: {table_ref}")
        return rows[0]["ddl"]
