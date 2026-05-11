"""DDL operations: retrieve CREATE TABLE statement."""
from __future__ import annotations

import logging
from typing import Dict, Any

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
        query = (
            f"SELECT ddl FROM `{table_ref.rsplit('.', 1)[0]}`.INFORMATION_SCHEMA.TABLES "
            f"WHERE table_name = '{table_ref.rsplit('.', 1)[1]}'"
        )
        result = self._client.query(query).result()
        rows = list(result)
        if not rows:
            raise ValueError(f"Table not found: {table_ref}")
        return rows[0]["ddl"]
