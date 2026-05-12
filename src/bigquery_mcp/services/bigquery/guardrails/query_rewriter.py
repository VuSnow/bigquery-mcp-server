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

        # Strip trailing comments for accurate LIMIT detection
        query_for_limit = cls._strip_trailing_comments(rewritten)

        # Check for existing LIMIT clause (with optional OFFSET)
        limit_match = re.search(
            r"\bLIMIT\s+(\d+)(\s+OFFSET\s+\d+)?\s*$",
            query_for_limit,
            re.IGNORECASE,
        )

        if limit_match:
            existing_limit = int(limit_match.group(1))
            if existing_limit > max_limit:
                # Cap the LAST LIMIT in the original string (outer query limit)
                # findall returns all matches; we want the last one
                all_matches = list(re.finditer(
                    r"\bLIMIT\s+(\d+)",
                    rewritten,
                    re.IGNORECASE,
                ))
                if all_matches:
                    last_match = all_matches[-1]
                    rewritten = (
                        rewritten[: last_match.start(1)]
                        + str(max_limit)
                        + rewritten[last_match.end(1):]
                    )
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
    def _strip_trailing_comments(cls, query: str) -> str:
        """Strip trailing SQL comments so LIMIT detection isn't fooled."""
        # Iteratively strip trailing line comments and block comments
        stripped = query.rstrip()
        changed = True
        while changed:
            changed = False
            # Strip trailing line comment: -- ...
            match = re.search(r"--[^\n]*$", stripped)
            if match:
                stripped = stripped[: match.start()].rstrip()
                changed = True
            # Strip trailing block comment: /* ... */
            if stripped.endswith("*/"):
                block_start = stripped.rfind("/*")
                if block_start >= 0:
                    stripped = stripped[:block_start].rstrip()
                    changed = True
        return stripped

    @classmethod
    def _is_aggregate_only(cls, query: str) -> bool:
        """Heuristic: if query is pure aggregate (COUNT/SUM/etc without GROUP BY), skip LIMIT.

        Only checks the OUTERMOST SELECT (last SELECT...FROM in CTE chains).
        """
        query_upper = query.upper().strip()

        # If it has GROUP BY, it can return many rows → needs LIMIT
        if "GROUP BY" in query_upper:
            return False

        # Find the outermost SELECT: for CTEs (WITH ... AS (...) SELECT ...)
        # we need the final SELECT, not inner ones.
        # Strategy: find the last top-level SELECT ... FROM
        outer_query = cls._extract_outer_select(query_upper)

        # Check if SELECT clause only contains aggregate functions
        select_match = re.search(r"SELECT\s+(.*?)\s+FROM", outer_query, re.DOTALL)
        if not select_match:
            return False

        select_clause = select_match.group(1)
        # Pure aggregates: COUNT(*), SUM(x), AVG(x), MIN(x), MAX(x) with optional alias
        agg_pattern = r"^(\s*(COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)(\s+AS\s+\w+)?\s*,?\s*)+$"
        return bool(re.match(agg_pattern, select_clause.strip()))

    @classmethod
    def _extract_outer_select(cls, query_upper: str) -> str:
        """Extract the outermost SELECT statement from a query (handles CTEs)."""
        # If starts with WITH, find the final SELECT after all CTE definitions
        if query_upper.strip().startswith("WITH"):
            # Walk through and find the last SELECT that's not inside parentheses
            depth = 0
            last_select_pos = -1
            i = 0
            while i < len(query_upper):
                if query_upper[i] == '(':
                    depth += 1
                elif query_upper[i] == ')':
                    depth -= 1
                elif depth == 0 and query_upper[i:i+6] == 'SELECT':
                    last_select_pos = i
                i += 1
            if last_select_pos >= 0:
                return query_upper[last_select_pos:]
        return query_upper
