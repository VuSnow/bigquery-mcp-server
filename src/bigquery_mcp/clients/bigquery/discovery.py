"""Discovery operations: sample rows, distinct values for column value awareness."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseBigQueryClient

logger = logging.getLogger(__name__)


class DiscoveryClient(BaseBigQueryClient):
    """Mixin for discovery operations that help Text2SQL agents understand data."""

    def get_sample_rows(
        self,
        table_ref: str,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get sample rows from a table for value awareness.

        Args:
            table_ref: Fully qualified table name.
            limit: Number of sample rows to return.
        """
        query = f"SELECT * FROM `{table_ref}` LIMIT {int(limit)}"
        result = self._client.query(query).result()
        return [dict(row) for row in result]

    def get_distinct_values(
        self,
        table_ref: str,
        column: str,
        limit: int = 50,
    ) -> List[Any]:
        """Get distinct values for a column to help agents pick correct filter values.

        Args:
            table_ref: Fully qualified table name.
            column: Column name to get distinct values for.
            limit: Maximum number of distinct values.
        """
        query = (
            f"SELECT DISTINCT `{column}` "
            f"FROM `{table_ref}` "
            f"WHERE `{column}` IS NOT NULL "
            f"ORDER BY `{column}` "
            f"LIMIT {int(limit)}"
        )
        result = self._client.query(query).result()
        return [row[0] for row in result]
