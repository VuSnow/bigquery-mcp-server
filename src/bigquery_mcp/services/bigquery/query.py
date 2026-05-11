"""Query service: execute query, dry run, explain error.

This is where the guardrails pipeline will be integrated (Phase 4).
For now, provides basic query execution with max_bytes_billed enforcement.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base import BaseBigQueryService
from bigquery_mcp.configs import configs

logger = logging.getLogger(__name__)


class QueryService(BaseBigQueryService):
    """Service for query execution with safety checks."""

    def execute_query(self, query: str) -> Dict[str, Any]:
        """Execute a SQL query with basic safety enforcement.

        The full guardrails pipeline (Phase 4) will add:
        - Rate limiting
        - Security validation
        - YAML guardrails
        - Query rewriting
        - PII masking
        - Audit logging

        Args:
            query: SQL query string.
        """
        logger.info("[execute_query] Query length=%d", len(query))

        if not query or not query.strip():
            return {"status": "error", "message": "Query cannot be empty."}

        query = query.strip()

        # Basic read-only enforcement
        query_lower = query.lower()
        allowed_starts = ("select", "with")
        if not any(query_lower.startswith(s) for s in allowed_starts):
            return {
                "status": "error",
                "message": "Only SELECT and WITH queries are allowed.",
            }

        client = self._ensure_connected()

        try:
            rows = client.execute_query(
                query,
                max_bytes_billed=configs.max_bytes_billed,
            )
        except Exception as e:
            logger.error("[execute_query] Query failed: %s", e)
            return {
                "status": "error",
                "message": f"Query execution failed: {str(e)}",
                "query": query,
            }

        logger.info("[execute_query] Returned %d rows", len(rows))
        return {
            "status": "ok",
            "rows": rows,
            "count": len(rows),
            "query": query,
        }

    def dry_run_query(self, query: str) -> Dict[str, Any]:
        """Dry-run a query to validate syntax and estimate cost.

        Args:
            query: SQL query string to validate.
        """
        logger.info("[dry_run_query] Query length=%d", len(query))

        if not query or not query.strip():
            return {"status": "error", "message": "Query cannot be empty."}

        query = query.strip()

        # Basic read-only enforcement
        query_lower = query.lower()
        allowed_starts = ("select", "with")
        if not any(query_lower.startswith(s) for s in allowed_starts):
            return {
                "status": "error",
                "message": "Only SELECT and WITH queries are allowed.",
            }

        client = self._ensure_connected()

        try:
            estimation = client.dry_run(
                query,
                max_bytes_billed=configs.max_bytes_billed,
            )
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

        # Common BigQuery error patterns and suggestions
        if "not found" in error_lower and "table" in error_lower:
            suggestions.append("Check table name spelling. Use list_tables to verify available tables.")
            suggestions.append("Ensure table is fully qualified: project.dataset.table or dataset.table")

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

    def get_security_status(self) -> Dict[str, Any]:
        """Get current security configuration and rate limit status."""
        return {
            "status": "ok",
            "read_only": configs.read_only,
            "max_bytes_billed": configs.max_bytes_billed,
            "rate_limit": {
                "max_calls": configs.rate_limit_max_calls,
                "window_seconds": configs.rate_limit_window_seconds,
            },
            "datasets_filter": configs.datasets_filter,
            "features_enabled": [
                "read_only_enforcement",
                "max_bytes_billed_cap",
                "table_name_validation",
                "dataset_filter",
            ],
        }
