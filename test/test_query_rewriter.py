"""Tests for QueryRewriter — LIMIT injection, capping, aggregate detection."""
import pytest

from bigquery_mcp.services.bigquery.guardrails.query_rewriter import QueryRewriter


class TestQueryRewriterLimitInjection:
    """Test automatic LIMIT injection."""

    def test_adds_default_limit(self):
        result = QueryRewriter.rewrite("SELECT * FROM dataset.table")
        assert "LIMIT 100" in result["rewritten_query"]
        assert len(result["modifications"]) == 1
        assert "Added LIMIT" in result["modifications"][0]

    def test_custom_default_limit(self):
        result = QueryRewriter.rewrite("SELECT * FROM dataset.table", default_limit=50)
        assert "LIMIT 50" in result["rewritten_query"]

    def test_preserves_existing_limit(self):
        result = QueryRewriter.rewrite("SELECT * FROM dataset.table LIMIT 20")
        assert "LIMIT 20" in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_preserves_original_query(self):
        original = "SELECT * FROM dataset.table"
        result = QueryRewriter.rewrite(original)
        assert result["original_query"] == original


class TestQueryRewriterLimitCapping:
    """Test max LIMIT enforcement."""

    def test_caps_excessive_limit(self):
        result = QueryRewriter.rewrite(
            "SELECT * FROM dataset.table LIMIT 50000",
            max_limit=1000,
        )
        assert "LIMIT 1000" in result["rewritten_query"]
        assert "capped" in result["modifications"][0].lower()

    def test_does_not_cap_within_max(self):
        result = QueryRewriter.rewrite(
            "SELECT * FROM dataset.table LIMIT 500",
            max_limit=1000,
        )
        assert "LIMIT 500" in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_caps_at_exact_max(self):
        result = QueryRewriter.rewrite(
            "SELECT * FROM dataset.table LIMIT 1001",
            max_limit=1000,
        )
        assert "LIMIT 1000" in result["rewritten_query"]

    def test_limit_case_insensitive(self):
        result = QueryRewriter.rewrite(
            "SELECT * FROM dataset.table limit 5000",
            max_limit=1000,
        )
        assert "1000" in result["rewritten_query"]

    def test_caps_outer_limit_not_subquery(self):
        """When query has LIMIT in subquery AND outer, only cap the outer."""
        query = "SELECT * FROM (SELECT id FROM t LIMIT 10) sub LIMIT 5000"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 10" in result["rewritten_query"]
        assert "LIMIT 1000" in result["rewritten_query"]
        assert "LIMIT 5000" not in result["rewritten_query"]

    def test_preserves_subquery_limit_when_outer_ok(self):
        """If outer LIMIT is within bounds, subquery LIMIT untouched."""
        query = "SELECT * FROM (SELECT id FROM t LIMIT 10) sub LIMIT 500"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 10" in result["rewritten_query"]
        assert "LIMIT 500" in result["rewritten_query"]
        assert len(result["modifications"]) == 0


class TestQueryRewriterAggregates:
    """Test aggregate detection (skip LIMIT for pure aggregates)."""

    def test_skip_limit_for_count(self):
        result = QueryRewriter.rewrite("SELECT COUNT(*) FROM dataset.table")
        assert "LIMIT" not in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_skip_limit_for_sum(self):
        result = QueryRewriter.rewrite("SELECT SUM(amount) FROM dataset.table")
        assert "LIMIT" not in result["rewritten_query"]

    def test_skip_limit_for_multi_aggregate(self):
        result = QueryRewriter.rewrite(
            "SELECT COUNT(*), AVG(price), MAX(qty) FROM dataset.table"
        )
        assert "LIMIT" not in result["rewritten_query"]

    def test_adds_limit_with_group_by(self):
        result = QueryRewriter.rewrite(
            "SELECT category, COUNT(*) FROM dataset.table GROUP BY category"
        )
        assert "LIMIT" in result["rewritten_query"]

    def test_adds_limit_for_non_aggregate_select(self):
        result = QueryRewriter.rewrite("SELECT name, email FROM dataset.table")
        assert "LIMIT" in result["rewritten_query"]

    def test_skip_limit_for_aliased_aggregate(self):
        """COUNT(*) AS total_count is still a pure aggregate — no LIMIT needed."""
        result = QueryRewriter.rewrite("SELECT COUNT(*) AS total_count FROM dataset.table")
        assert "LIMIT" not in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_skip_limit_for_multiple_aliased_aggregates(self):
        result = QueryRewriter.rewrite(
            "SELECT COUNT(*) AS cnt, SUM(amount) AS total, AVG(price) AS avg_price FROM orders"
        )
        assert "LIMIT" not in result["rewritten_query"]
        assert len(result["modifications"]) == 0


class TestQueryRewriterCTE:
    """Test CTE (WITH) query handling."""

    def test_cte_with_aggregate_inner_non_aggregate_outer(self):
        """CTE inner is aggregate but outer SELECT * should still get LIMIT."""
        query = "WITH cte AS (SELECT COUNT(*) AS cnt FROM t) SELECT * FROM cte"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT" in result["rewritten_query"]

    def test_cte_with_non_aggregate_outer(self):
        query = "WITH filtered AS (SELECT id, name FROM t WHERE active = true) SELECT id, name FROM filtered"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT" in result["rewritten_query"]

    def test_cte_with_pure_aggregate_outer(self):
        """CTE outer is pure aggregate → no LIMIT needed."""
        query = "WITH base AS (SELECT * FROM t) SELECT COUNT(*) FROM base"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT" not in result["rewritten_query"]

    def test_multiple_ctes(self):
        query = (
            "WITH a AS (SELECT COUNT(*) FROM t1), "
            "b AS (SELECT id FROM t2) "
            "SELECT * FROM b"
        )
        result = QueryRewriter.rewrite(query)
        assert "LIMIT" in result["rewritten_query"]


class TestQueryRewriterTrailingComments:
    """Test LIMIT detection with trailing comments."""

    def test_limit_with_trailing_line_comment(self):
        query = "SELECT * FROM t LIMIT 5000\n-- this is a comment"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 1000" in result["rewritten_query"]
        assert "capped" in result["modifications"][0].lower()

    def test_limit_with_trailing_block_comment(self):
        query = "SELECT * FROM t LIMIT 5000 /* cap me */"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 1000" in result["rewritten_query"]

    def test_no_limit_with_trailing_comment_adds_default(self):
        query = "SELECT * FROM t\n-- just a comment"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT 100" in result["rewritten_query"]
        assert "Added LIMIT" in result["modifications"][0]

    def test_valid_limit_with_comment_not_modified(self):
        query = "SELECT * FROM t LIMIT 50\n-- keep this"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 50" in result["rewritten_query"]
        assert len(result["modifications"]) == 0


class TestQueryRewriterEdgeCases:
    """Edge cases: string literals, huge numbers, multiline, LIMIT 0."""

    def test_limit_in_string_literal_ignored(self):
        """LIMIT inside a string literal should NOT be treated as a real LIMIT."""
        query = "SELECT * FROM t WHERE note = 'LIMIT 5000'"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "Added LIMIT" in result["modifications"][0]

    def test_huge_limit_capped(self):
        """Extremely large LIMIT (2^63) should be capped without overflow."""
        query = f"SELECT * FROM t LIMIT {2**63}"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "capped" in result["modifications"][0].lower()
        assert "LIMIT 1000" in result["rewritten_query"]

    def test_limit_zero_preserved(self):
        """LIMIT 0 is valid (returns no rows) and should not be capped."""
        query = "SELECT * FROM t LIMIT 0"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 0" in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_multiline_query_gets_limit(self):
        query = "SELECT\n  id,\n  name\nFROM\n  dataset.users\nWHERE\n  active = true"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT 100" in result["rewritten_query"]

    def test_cte_aliased_aggregate_no_limit(self):
        """CTE with aliased aggregate in outer SELECT should skip LIMIT."""
        query = "WITH base AS (SELECT * FROM t) SELECT COUNT(*) AS total FROM base"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT" not in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_case_with_aggregate_gets_limit(self):
        """CASE WHEN aggregate is not detected as pure aggregate — LIMIT is harmlessly added."""
        query = "SELECT CASE WHEN COUNT(*) > 0 THEN 1 ELSE 0 END FROM t"
        result = QueryRewriter.rewrite(query)
        assert "LIMIT" in result["rewritten_query"]

    def test_order_by_limit_with_trailing_comment(self):
        """ORDER BY + LIMIT + trailing comment: LIMIT is detected correctly."""
        query = "SELECT * FROM t ORDER BY id LIMIT 500 -- pagination"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 500" in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_limit_in_column_alias_not_confused(self):
        """Column alias containing 'limit' word should not confuse detection."""
        query = "SELECT id, name AS limit_name FROM t"
        result = QueryRewriter.rewrite(query)
        assert "Added LIMIT" in result["modifications"][0]

    def test_whitespace_only_query(self):
        """Whitespace-only query still gets LIMIT appended (service layer rejects before this)."""
        result = QueryRewriter.rewrite("   ")
        assert "LIMIT" in result["rewritten_query"]

    def test_limit_with_offset_preserved(self):
        """LIMIT with OFFSET should be preserved without adding another LIMIT."""
        query = "SELECT * FROM t LIMIT 50 OFFSET 100"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 50" in result["rewritten_query"]
        assert "OFFSET 100" in result["rewritten_query"]
        assert len(result["modifications"]) == 0

    def test_limit_with_offset_capped(self):
        """Excessive LIMIT with OFFSET should be capped."""
        query = "SELECT * FROM t LIMIT 5000 OFFSET 10"
        result = QueryRewriter.rewrite(query, max_limit=1000)
        assert "LIMIT 1000" in result["rewritten_query"]
        assert "OFFSET 10" in result["rewritten_query"]
