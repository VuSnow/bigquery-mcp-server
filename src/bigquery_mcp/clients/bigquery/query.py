"""Query operations: execute query, dry run, estimate cost."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from google.cloud import bigquery

from .base import BaseBigQueryClient

logger = logging.getLogger(__name__)


class QueryClient(BaseBigQueryClient):
    """Mixin for query execution operations."""

    def execute_query(
        self,
        query: str,
        max_bytes_billed: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a SQL query and return results as list of dicts.

        Args:
            query: SQL query string.
            max_bytes_billed: Override max bytes billed for this query.
            timeout: Query timeout in seconds.
        """
        job_config = bigquery.QueryJobConfig(
            maximum_bytes_billed=max_bytes_billed,
        )
        query_job = self._client.query(query, job_config=job_config)
        result = query_job.result(timeout=timeout)
        return [dict(row) for row in result]

    def dry_run(
        self,
        query: str,
        max_bytes_billed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Dry-run a query to validate syntax and estimate cost.

        Args:
            query: SQL query string.
            max_bytes_billed: Override max bytes billed for this query.
        """
        job_config = bigquery.QueryJobConfig(
            dry_run=True,
            use_query_cache=False,
            maximum_bytes_billed=max_bytes_billed,
        )
        query_job = self._client.query(query, job_config=job_config)
        result = {
            "total_bytes_processed": query_job.total_bytes_processed,
            "total_bytes_billed": query_job.total_bytes_billed,
            "cache_hit": query_job.cache_hit,
            "statement_type": query_job.statement_type,
            "referenced_tables": [
                {
                    "project": ref.project,
                    "dataset_id": ref.dataset_id,
                    "table_id": ref.table_id,
                }
                for ref in (query_job.referenced_tables or [])
            ],
        }
        # Include output schema if available
        if query_job.schema:
            result["schema"] = [
                {"name": field.name, "type": field.field_type}
                for field in query_job.schema
            ]
        return result

    def get_distinct_values(
        self,
        table_ref: str,
        column: str,
        limit: int = 50,
        timeout: Optional[float] = 60.0,
    ) -> List[Any]:
        """Get distinct values for a column.

        Args:
            table_ref: Fully qualified table name.
            column: Column name to get distinct values for.
            limit: Maximum number of distinct values.
            timeout: Query timeout in seconds.
        """
        query = (
            f"SELECT DISTINCT `{column}` "
            f"FROM `{table_ref}` "
            f"WHERE `{column}` IS NOT NULL "
            f"ORDER BY `{column}` "
            f"LIMIT {int(limit)}"
        )
        result = self._client.query(query).result(timeout=timeout)
        return [row[0] for row in result]
