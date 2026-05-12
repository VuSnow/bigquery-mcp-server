"""Query service: execute query, dry run, explain error, get status.

Handles read-only enforcement, connection routing, and full guardrails pipeline.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .base import BaseBigQueryService
from .guardrails import GuardrailsPipeline

logger = logging.getLogger(__name__)


class QueryService(BaseBigQueryService):
    """Service for query execution with guardrails pipeline and multi-connection routing."""

    _pipeline: Optional[GuardrailsPipeline] = None

    def _get_pipeline(self) -> GuardrailsPipeline:
        """Lazy-init the guardrails pipeline from YAML config."""
        if self._pipeline is None:
            from bigquery_mcp.utils.config_parser import config_parser
            guardrails_config = config_parser.get_guardrails()
            pii_rules = config_parser.get_pii_rules()
            self._pipeline = GuardrailsPipeline(guardrails_config, pii_rules)
        return self._pipeline

    def execute_query(self, query: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """Execute a SQL query with full guardrails pipeline.

        Pipeline: rate limit → security → rewrite → execute → PII mask → audit.

        Args:
            query: SQL query string.
            connection: Optional explicit connection to route to.
        """
        logger.info("[execute_query] Query length=%d", len(query))

        if not query or not query.strip():
            return {"status": "error", "message": "Query cannot be empty."}

        query = query.strip()
        conn_name = self._resolve_connection_name(connection=connection)
        guardrails = self._get_guardrails(connection)

        # Read-only enforcement (fast check before pipeline)
        if guardrails.get("read_only", True):
            query_lower = query.lower()
            allowed_starts = ("select", "with")
            if not any(query_lower.startswith(s) for s in allowed_starts):
                return {
                    "status": "error",
                    "message": "Only SELECT and WITH queries are allowed.",
                }

        # Guardrails pipeline: pre-execute
        pipeline = self._get_pipeline()
        pre_result = pipeline.pre_execute(query, conn_name)

        if not pre_result["allowed"]:
            return {
                "status": "error",
                "message": pre_result["error"],
                "stage": pre_result["stage"],
            }

        executed_query = pre_result["query"]
        modifications = pre_result["modifications"]

        # Execute
        client = self._get_client(connection=connection)
        max_bytes = guardrails.get("max_bytes_billed", 10_737_418_240)

        try:
            rows = client.execute_query(executed_query, max_bytes_billed=max_bytes)
        except Exception as e:
            logger.error("[execute_query] Query failed: %s", e)
            from .guardrails import AuditLogger
            AuditLogger.log_query(
                query=executed_query, connection=conn_name,
                status="error", error=str(e),
            )
            return {
                "status": "error",
                "message": f"Query execution failed: {str(e)}",
                "query": executed_query,
            }

        # Guardrails pipeline: post-execute (PII masking + audit)
        post_result = pipeline.post_execute(rows, conn_name, executed_query, modifications)

        logger.info("[execute_query] Returned %d rows via '%s'", len(post_result["rows"]), conn_name)
        result: Dict[str, Any] = {
            "status": "ok",
            "connection": conn_name,
            "rows": post_result["rows"],
            "count": len(post_result["rows"]),
            "query": executed_query,
        }
        if modifications:
            result["modifications"] = modifications
        if post_result["masked_fields"]:
            result["masked_fields"] = post_result["masked_fields"]

        return result

    def dry_run_query(self, query: str, connection: Optional[str] = None) -> Dict[str, Any]:
        """Dry-run a query to validate syntax and estimate cost.

        Applies security validation but skips rewrite/PII/audit since no data is returned.

        Args:
            query: SQL query string to validate.
            connection: Optional explicit connection to route to.
        """
        logger.info("[dry_run_query] Query length=%d", len(query))

        if not query or not query.strip():
            return {"status": "error", "message": "Query cannot be empty."}

        query = query.strip()
        conn_name = self._resolve_connection_name(connection=connection)
        guardrails = self._get_guardrails(connection)

        # Read-only enforcement
        if guardrails.get("read_only", True):
            query_lower = query.lower()
            allowed_starts = ("select", "with")
            if not any(query_lower.startswith(s) for s in allowed_starts):
                return {
                    "status": "error",
                    "message": "Only SELECT and WITH queries are allowed.",
                }

        # Security validation only (no rewrite for dry-run)
        from .guardrails import SecurityValidator
        max_length = guardrails.get("max_query_length", 10_000)
        sec_result = SecurityValidator.validate(query, max_length=max_length)
        if not sec_result["valid"]:
            return {"status": "error", "message": sec_result["error"]}

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
            "connection": conn_name,
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
        pipeline = self._get_pipeline()

        return {
            "status": "ok",
            "connections": connections,
            "default_connection": config_parser.get_default_connection_name(),
            "guardrails": {
                "read_only": guardrails.get("read_only", True),
                "default_limit": guardrails.get("default_limit", 100),
                "max_limit": guardrails.get("max_limit", 1000),
                "max_bytes_billed": guardrails.get("max_bytes_billed"),
                "max_query_length": guardrails.get("max_query_length", 10_000),
                "forbid_cross_connection": guardrails.get("forbid_cross_connection", False),
                "rate_limit": pipeline.rate_limiter.get_status(),
            },
            "blocked_tables": config_parser.get_blocked_tables(),
            "pii_rules_count": len(config_parser.get_pii_rules()),
        }
