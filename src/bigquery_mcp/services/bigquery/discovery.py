"""Discovery service: search tables, join rules, column values, example queries.

Discovery tools read from YAML config to provide Text2SQL agents
with table relationships, valid column values, and SQL examples.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseBigQueryService

logger = logging.getLogger(__name__)


class DiscoveryService(BaseBigQueryService):
    """Service for Text2SQL discovery operations (YAML config + live queries)."""

    def _get_config_parser(self):
        """Lazy import config parser to avoid circular imports."""
        from bigquery_mcp.utils.config_parser import config_parser
        return config_parser

    def search_tables(self, keyword: str) -> Dict[str, Any]:
        """Search tables by keyword matching against name, purpose, and tags.

        Args:
            keyword: Search term to match against table metadata.
        """
        logger.info("[search_tables] keyword='%s'", keyword)
        if not keyword or not keyword.strip():
            raise ValueError("Search keyword cannot be empty.")

        keyword_lower = keyword.lower().strip()
        config = self._get_config_parser()
        tables = config.get_tables()
        matches = []

        for table in tables:
            name = table.get("name", "").lower()
            purpose = table.get("purpose", "").lower()
            tags = [t.lower() for t in table.get("tags", [])]

            if (
                keyword_lower in name
                or keyword_lower in purpose
                or any(keyword_lower in tag for tag in tags)
            ):
                matches.append({
                    "name": table.get("name"),
                    "purpose": table.get("purpose"),
                    "tags": table.get("tags", []),
                    "partition_by": table.get("partition_by"),
                })

        logger.info("[search_tables] Found %d matches for '%s'", len(matches), keyword)
        return {"status": "ok", "matches": matches, "count": len(matches)}

    def get_join_rules(self, table_name: str) -> Dict[str, Any]:
        """Get join relationships for a table from YAML config.

        Args:
            table_name: Table to get join rules for.
        """
        logger.info("[get_join_rules] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        config = self._get_config_parser()
        table_config = config.get_table_config(table_name)

        if not table_config:
            return {"status": "not_found", "message": f"Table '{table_name}' not found in config."}

        join_rules = table_config.get("join_rules", [])
        logger.info("[get_join_rules] Found %d join rules for '%s'", len(join_rules), table_name)
        return {"status": "ok", "table": table_name, "join_rules": join_rules}

    def get_column_values(
        self,
        table_name: str,
        column: str,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get distinct values for a column (live query to BigQuery).

        Args:
            table_name: Table containing the column.
            column: Column name to get values for.
            limit: Max number of distinct values.
        """
        logger.info("[get_column_values] table='%s', column='%s', limit=%d", table_name, column, limit)
        table_name = self._validate_table_name(table_name)
        column = self._validate_column_name(column)
        limit = max(1, min(limit, 200))
        client = self._ensure_connected()

        values = client.get_distinct_values(table_name, column, limit)
        logger.info("[get_column_values] Found %d values for '%s.%s'", len(values), table_name, column)
        return {
            "status": "ok",
            "table": table_name,
            "column": column,
            "values": values,
            "count": len(values),
        }

    def get_example_queries(self, table_name: str) -> Dict[str, Any]:
        """Get example SQL queries for a table from YAML config.

        Args:
            table_name: Table to get examples for.
        """
        logger.info("[get_example_queries] table='%s'", table_name)
        table_name = self._validate_table_name(table_name)
        config = self._get_config_parser()
        table_config = config.get_table_config(table_name)

        if not table_config:
            return {"status": "not_found", "message": f"Table '{table_name}' not found in config."}

        examples = table_config.get("example_queries", [])
        logger.info("[get_example_queries] Found %d examples for '%s'", len(examples), table_name)
        return {"status": "ok", "table": table_name, "examples": examples, "count": len(examples)}
