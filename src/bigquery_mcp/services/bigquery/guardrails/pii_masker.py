"""PII masker — hash or redact sensitive columns in query results."""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class PIIMasker:
    """Masks PII fields in query result rows based on configured rules."""

    def __init__(self, rules: List[Dict[str, str]]) -> None:
        """Initialize with PII rules.

        Args:
            rules: List of {"column": "email", "method": "hash"|"redact"}
        """
        self._rules = {r["column"]: r["method"] for r in rules if "column" in r and "method" in r}

    @property
    def has_rules(self) -> bool:
        return len(self._rules) > 0

    def mask_rows(self, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Mask PII fields in result rows.

        Args:
            rows: List of row dicts from query results.

        Returns:
            Dict with masked_rows, masked_fields list, and count of modifications.
        """
        if not self._rules or not rows:
            return {"rows": rows, "masked_fields": [], "modifications": 0}

        masked_fields: list[str] = []
        modifications = 0

        for row in rows:
            for column, method in self._rules.items():
                if column in row and row[column] is not None:
                    if column not in masked_fields:
                        masked_fields.append(column)
                    row[column] = self._apply_mask(row[column], method)
                    modifications += 1

        if masked_fields:
            logger.info("[pii] Masked %d values across fields: %s", modifications, masked_fields)

        return {
            "rows": rows,
            "masked_fields": masked_fields,
            "modifications": modifications,
        }

    @staticmethod
    def _apply_mask(value: Any, method: str) -> str:
        """Apply masking method to a single value."""
        if method == "hash":
            return hashlib.sha256(str(value).encode()).hexdigest()[:16]
        elif method == "redact":
            return "***REDACTED***"
        else:
            return "***MASKED***"
