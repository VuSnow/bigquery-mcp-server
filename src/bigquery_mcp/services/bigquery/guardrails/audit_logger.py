"""Audit logger — structured logging for security-relevant query events."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("bigquery_mcp.audit")


class AuditLogger:
    """Logs security-relevant events for audit trail."""

    @classmethod
    def log_query(
        cls,
        *,
        query: str,
        connection: str,
        status: str,
        rows_returned: int = 0,
        bytes_processed: Optional[int] = None,
        modifications: Optional[list[str]] = None,
        masked_fields: Optional[list[str]] = None,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Log a query execution event.

        Returns the audit record for inclusion in response if needed.
        """
        record = {
            "timestamp": time.time(),
            "event": "query_execution",
            "connection": connection,
            "query_length": len(query),
            "status": status,
            "rows_returned": rows_returned,
        }

        if bytes_processed is not None:
            record["bytes_processed"] = bytes_processed
        if modifications:
            record["modifications"] = modifications
        if masked_fields:
            record["masked_fields"] = masked_fields
        if error:
            record["error"] = error[:200]

        if status == "ok":
            logger.info("[audit] query_ok connection=%s rows=%d", connection, rows_returned)
        else:
            logger.warning("[audit] query_failed connection=%s error=%s", connection, error or "unknown")

        return record

    @classmethod
    def log_blocked(
        cls,
        *,
        query: str,
        connection: str,
        reason: str,
        stage: str,
    ) -> Dict[str, Any]:
        """Log a blocked query event (rate limit, security, guardrails)."""
        record = {
            "timestamp": time.time(),
            "event": "query_blocked",
            "connection": connection,
            "query_length": len(query),
            "reason": reason,
            "stage": stage,
        }

        logger.warning(
            "[audit] query_blocked connection=%s stage=%s reason=%s",
            connection, stage, reason,
        )
        return record
