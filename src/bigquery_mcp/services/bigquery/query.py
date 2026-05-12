"""Query service: execute query, dry run, explain error, get status.

Handles read-only enforcement, connection routing, and guardrails integration.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base import BaseBigQueryService

logger = logging.getLogger(__name__)


class QueryService(BaseBigQueryService):
    """Service for query execution with safety checks and multi-connection routing."""

    def execute_query(self, query: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """Execute a SQL query with safety enforcement.

        Args:
            query: SQL query string.
            connection: Optional explicit connection to route to.
        """
        logger.info("[execute_query] Query length=%d", len(query))

        if not query or not query.strip():
            return {"status": "error", "message": "Query cannot be empty."}

        query = query.strip()

        # Read-only enforcement
        guardrails = self._get_guardrails(connection)
        if guardrails.get("read_only", True):
            query_lower = query.lower()
            allowed_starts = ("select", "with")
            if not any(query_lower.startswith(s) for s in allowed_starts):
                return {
                    "status": "error",
                    "message": "Only SELECT and WITH queries are allowed.",
                }

        # Get client (auto-route if no explicit connection)
        client = self._get_client(connection=connection)
        conn_name = self._resolve_connection_name(connection=connection)

        max_bytes = guardrails.get("max_bytes_billed", 10_737_418_240)

        try:
            rows = client.execute_query(query, max_bytes_billed=max_bytes)
        except Exception as e:
            logger.error("[execute_query] Query failed: %s", e)
            return {
                "status": "error",
                "message": f"Query execution failed: {str(e)}",
                "query": query,
            }

        logger.info("[execute_query] Returned %d rows via '%s'", len(rows), conn_name)
        return {
            "status": "ok",
            "connection": conn_name,
            "rows": rows,
            "count": len(rows),
            "query": query,
        }

    def dry_run_query(self, query: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """Dry-run a query to validate syntax and estimate cost.

        Args:
            query: SQL query string to validate.
            connection: Optional explicit connection to route to.
        """
        logger.info("[dry_run_query] Query length=%d", len(query))

        if not query or not query.strip():
            return {"status": "error", "message": "Query cannot be empty."}

        query = query.strip()

        # Read-only enforcement
        guardrails = self._get_guardrails(connection)
        if guardrails.get("read_only", True):
            query_lower = query.lower()
            allowed_starts = ("select", "with")
            if not any(query_lower.startswith(s) for s in allowed_starts):
                return {
                    "status": "error",
                    "message": "Only SELECT and WITH queries are allowed.",
                }

        client = self._get_client(connection=connection)
        max_bytes = guardrails.get("max_bytes_billed", 10_737_418_240)

        try:
            estimation = client.dry_run(query, max_bytes_billed=max_bytes)
        except Exception as e:
            logger.error("[dry_run_query] Dry run failed: %s", e)
            return {
                "status": "error",
                "message": f"Dry run failed: {str(e)}",
                "query": query,
            }

        logger.info(
            "[dry_run_query] Estimated %d bytes processed",
            estimation.get("total_bytes_processed", 0),
        )
        return {
            "status": "ok",
            "valid": True,
            "query": query,
            "estimation": estimation,
        }

    def explain_query_error(self, error_message: str, query: str) -> Dict[str, Any]:
        """Analyze a BigQuery error and suggest fixes for agent retry loops.

        Args:
            error_message: The error message from a failed query.
            query: The SQL query that produced the error.
        """
        logger.info("[explain_query_error] error='%s'", error_message[:100])

        if not error_message or not query:
            return {"status": "error", "message": "Both error_message and query are required."}

        error_lower = error_message.lower()
        suggestions: list[str] = []

        if "not found" in error_lower and "table" in error_lower:
            suggestions.append("Check table name spelling. Use list_tables to verify available tables.")
            suggestions.append("Ensure table is fully qualified: dataset.table")

        elif "not found" in error_lower and "column" in error_lower:
            suggestions.append("Check column name. Use get_table_schema to see available columns.")

        elif "syntax error" in error_lower:
            suggestions.append("Check SQL syntax. BigQuery uses Standard SQL by default.")
            suggestions.append("Verify function names are BigQuery-compatible (e.g., DATE_SUB, TIMESTAMP_DIFF).")

        elif "access denied" in error_lower or "permission" in error_lower:
            suggestions.append("The service account may not have access to this table/dataset.")

        elif "exceeded" in error_lower and "bytes" in error_lower:
            suggestions.append("Query scans too much data. Add partition filters or reduce date range.")
            suggestions.append("Use WHERE clauses on partitioned columns to limit scan size.")

        elif "ambiguous" in error_lower:
            suggestions.append("Use fully qualified column names with table alias (e.g., t.column_name).")

        elif "division by zero" in error_lower:
            suggestions.append("Use SAFE_DIVIDE(a, b) instead of a/b to handle zero denominators.")

        else:
            suggestions.append("Review the error message and check BigQuery documentation.")
            suggestions.append("Use dry_run_query to validate the corrected query before executing.")

        return {
            "status": "ok",
            "error_message": error_message,
            "query": query,
            "suggestions": suggestions,
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current server configuration, connections health, and guardrails."""
        from bigquery_mcp.services.connection_manager import connection_manager
        from bigquery_mcp.utils.config_parser import config_parser

        guardrails = config_parser.get_guardrails()
        connections = connection_manager.get_status()

        return {
            "status": "ok",
            "connections": connections,
            "default_connection": config_parser.get_default_connection_name(),
            "guardrails": {
                "read_only": guardrails.get("read_only", True),
                "default_limit": guardrails.get("default_limit", 100),
                "max_limit": guardrails.get("max_limit", 1000),
                "max_bytes_billed": guardrails.get("max_bytes_billed"),
                "forbid_cross_connection": guardrails.get("forbid_cross_connection", False),
                "rate_limit": guardrails.get("rate_limit", {}),
            },
            "blocked_tables": config_parser.get_blocked_tables(),
            "pii_rules_count": len(config_parser.get_pii_rules()),
        }
