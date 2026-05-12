"""Query rewriter — auto LIMIT injection, max limit enforcement."""
from __future__ import annotations

import re
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class QueryRewriter:
    """Rewrites queries to enforce limits and safety constraints."""

    @classmethod
    def rewrite(
        cls,
        query: str,
        default_limit: int = 100,
        max_limit: int = 1000,
    ) -> Dict[str, Any]:
        """Rewrite query: inject or cap LIMIT.

        Args:
            query: SQL query string.
            default_limit: LIMIT to add when query has none.
            max_limit: Maximum LIMIT value (caps if higher).

        Returns:
            Dict with rewritten_query, modifications list, and original_query.
        """
        modifications: list[str] = []
        rewritten = query.strip()

        # Check for existing LIMIT clause
        limit_match = re.search(
            r"\bLIMIT\s+(\d+)\s*$",
            rewritten,
            re.IGNORECASE,
        )

        if limit_match:
            existing_limit = int(limit_match.group(1))
            if existing_limit > max_limit:
                # Cap the limit
                rewritten = rewritten[: limit_match.start(1)] + str(max_limit) + rewritten[limit_match.end(1):]
                modifications.append(f"LIMIT capped from {existing_limit} to {max_limit}")
                logger.info("[rewriter] Capped LIMIT %d → %d", existing_limit, max_limit)
        else:
            # No LIMIT found — add default
            # Don't add LIMIT to subqueries or CTEs without final SELECT
            if not cls._is_aggregate_only(rewritten):
                rewritten = f"{rewritten}\nLIMIT {default_limit}"
                modifications.append(f"Added LIMIT {default_limit}")
                logger.info("[rewriter] Injected LIMIT %d", default_limit)

        return {
            "rewritten_query": rewritten,
            "modifications": modifications,
            "original_query": query,
        }

    @classmethod
    def _is_aggregate_only(cls, query: str) -> bool:
        """Heuristic: if query is pure aggregate (COUNT/SUM/etc without GROUP BY), skip LIMIT."""
        query_upper = query.upper().strip()

        # If it has GROUP BY, it can return many rows → needs LIMIT
        if "GROUP BY" in query_upper:
            return False

        # Check if SELECT clause only contains aggregate functions
        select_match = re.search(r"SELECT\s+(.*?)\s+FROM", query_upper, re.DOTALL)
        if not select_match:
            return False

        select_clause = select_match.group(1)
        # Pure aggregates: COUNT(*), SUM(x), AVG(x), MIN(x), MAX(x)
        agg_pattern = r"^(\s*(COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)\s*,?\s*)+$"
        return bool(re.match(agg_pattern, select_clause.strip()))
