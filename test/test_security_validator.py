"""Tests for SecurityValidator — forbidden keywords, injection patterns, length."""
import pytest

from bigquery_mcp.services.bigquery.guardrails.security_validator import SecurityValidator


class TestSecurityValidatorBasic:
    """Test basic validation rules."""

    def test_valid_select(self):
        result = SecurityValidator.validate("SELECT * FROM dataset.table")
        assert result["valid"] is True

    def test_valid_with_cte(self):
        result = SecurityValidator.validate(
            "WITH cte AS (SELECT 1) SELECT * FROM cte"
        )
        assert result["valid"] is True

    def test_valid_show(self):
        result = SecurityValidator.validate("SHOW TABLES")
        assert result["valid"] is True

    def test_valid_explain(self):
        result = SecurityValidator.validate("EXPLAIN SELECT 1")
        assert result["valid"] is True

    def test_empty_query(self):
        result = SecurityValidator.validate("")
        assert result["valid"] is False
        assert "Empty" in result["error"]

    def test_whitespace_only(self):
        result = SecurityValidator.validate("   ")
        assert result["valid"] is False

    def test_query_too_long(self):
        result = SecurityValidator.validate("SELECT " + "x" * 200, max_length=100)
        assert result["valid"] is False
        assert "too long" in result["error"]

    def test_query_at_max_length(self):
        query = "SELECT 1"
        result = SecurityValidator.validate(query, max_length=len(query))
        assert result["valid"] is True


class TestSecurityValidatorForbiddenKeywords:
    """Test forbidden keyword detection."""

    @pytest.mark.parametrize(
        "query",
        [
            "DROP TABLE dataset.table",
            "DELETE FROM dataset.table WHERE id=1",
            "INSERT INTO dataset.table VALUES (1)",
            "UPDATE dataset.table SET x=1",
            "TRUNCATE TABLE dataset.table",
            "ALTER TABLE dataset.table ADD COLUMN x INT",
            "CREATE TABLE dataset.table (id INT)",
            "GRANT SELECT ON dataset.table TO user",
        ],
    )
    def test_forbidden_ddl_dml(self, query):
        result = SecurityValidator.validate(query)
        assert result["valid"] is False

    def test_forbidden_keyword_in_select(self):
        # "DROP" as a keyword inside a SELECT body
        result = SecurityValidator.validate("SELECT drop FROM dataset.table")
        assert result["valid"] is False
        assert "Forbidden" in result["error"]

    def test_keyword_in_string_literal_ignored(self):
        # "DROP" inside a string literal should be stripped by _remove_string_literals
        result = SecurityValidator.validate("SELECT * FROM dataset.table WHERE name = 'DROP'")
        assert result["valid"] is True

    def test_backtick_literal_ignored(self):
        result = SecurityValidator.validate("SELECT * FROM `dataset`.`table` WHERE x = 'DELETE'")
        assert result["valid"] is True


class TestSecurityValidatorInjection:
    """Test SQL injection pattern detection."""

    def test_semicolon_injection(self):
        result = SecurityValidator.validate("SELECT 1; DROP TABLE foo")
        assert result["valid"] is False

    def test_load_data(self):
        result = SecurityValidator.validate("SELECT * FROM t WHERE load data infile '/etc/passwd'")
        assert result["valid"] is False

    def test_xp_cmdshell(self):
        result = SecurityValidator.validate("SELECT * FROM t WHERE xp_cmdshell('cmd')")
        assert result["valid"] is False


class TestSecurityValidatorDangerousFunctions:
    """Test dangerous function detection."""

    def test_sleep_function(self):
        result = SecurityValidator.validate("SELECT sleep(10) FROM t")
        assert result["valid"] is False

    def test_benchmark_function(self):
        result = SecurityValidator.validate("SELECT benchmark(1000, SHA1('test')) FROM t")
        assert result["valid"] is False

    def test_safe_query_with_similar_words(self):
        # "selection" contains "select" but should not trigger "set"
        result = SecurityValidator.validate("SELECT count(*) FROM dataset.table")
        assert result["valid"] is True


class TestSecurityValidatorComments:
    """Test that SQL comments containing forbidden keywords don't cause false positives."""

    def test_line_comment_with_delete(self):
        result = SecurityValidator.validate(
            "SELECT * FROM orders -- delete old records later"
        )
        assert result["valid"] is True

    def test_line_comment_with_update(self):
        result = SecurityValidator.validate(
            "SELECT * FROM t WHERE status = 'active' -- update: added filter"
        )
        assert result["valid"] is True

    def test_block_comment_with_drop(self):
        result = SecurityValidator.validate(
            "SELECT * FROM orders /* drop this column later */"
        )
        assert result["valid"] is True

    def test_multiline_block_comment(self):
        result = SecurityValidator.validate(
            "SELECT * FROM orders\n/* TODO:\n  - delete old rows\n  - truncate staging */"
        )
        assert result["valid"] is True

    def test_real_forbidden_keyword_not_in_comment(self):
        # Actual DROP outside comment should still be blocked
        result = SecurityValidator.validate("DROP TABLE t -- this is bad")
        assert result["valid"] is False

    def test_hash_comment_with_keyword(self):
        result = SecurityValidator.validate(
            "SELECT * FROM t # kill this query if slow"
        )
        assert result["valid"] is True


class TestSecurityValidatorEscapedQuotes:
    """Test handling of escaped/doubled quotes in string literals."""

    def test_doubled_single_quote_with_keyword(self):
        # BigQuery: 'it''s a DROP TABLE' — keyword inside escaped string
        result = SecurityValidator.validate(
            "SELECT * FROM t WHERE name = 'it''s a DROP TABLE'"
        )
        assert result["valid"] is True

    def test_doubled_single_quote_complex(self):
        result = SecurityValidator.validate(
            "SELECT * FROM t WHERE msg = 'don''t delete me'"
        )
        assert result["valid"] is True

    def test_actual_keyword_outside_escaped_string(self):
        # Real DELETE outside string should still be blocked
        result = SecurityValidator.validate(
            "DELETE FROM t WHERE name = 'it''s ok'"
        )
        assert result["valid"] is False

    def test_doubled_double_quote_with_keyword(self):
        result = SecurityValidator.validate(
            'SELECT * FROM t WHERE desc = "she said ""drop it"""'
        )
        assert result["valid"] is True


class TestSecurityValidatorExoticBypass:
    """Test exotic SQL injection bypass attempts."""

    def test_unicode_in_query(self):
        """Unicode characters should not crash validation."""
        result = SecurityValidator.validate(
            "SELECT name FROM users WHERE city = 'Hà Nội'"
        )
        assert result["valid"] is True

    def test_semicolon_with_drop(self):
        """Semicolon followed by DROP should be blocked."""
        result = SecurityValidator.validate("SELECT 1; DROP TABLE t")
        assert result["valid"] is False

    def test_nested_escaped_quotes_with_keywords(self):
        """Multiple escaped quotes containing keywords should be safe."""
        result = SecurityValidator.validate(
            "SELECT * FROM t WHERE x = 'it''s a DROP TABLE isn''t it'"
        )
        assert result["valid"] is True

    def test_backtick_reserved_column_names(self):
        """Backtick-escaped column names with reserved words are valid."""
        result = SecurityValidator.validate(
            "SELECT `drop`, `delete` FROM t"
        )
        assert result["valid"] is True

    def test_comment_before_drop_blocked(self):
        """DROP after comment removal should still be blocked."""
        result = SecurityValidator.validate(
            "SELECT 1 /* harmless */ DROP TABLE t"
        )
        assert result["valid"] is False

    def test_crlf_injection_blocked(self):
        """CRLF followed by DROP is blocked."""
        result = SecurityValidator.validate(
            "SELECT 1\r\nDROP TABLE t"
        )
        assert result["valid"] is False

    def test_null_byte_blocked(self):
        """Null byte in query should not bypass validation."""
        result = SecurityValidator.validate(
            "SELECT 1\x00DROP TABLE t"
        )
        assert result["valid"] is False

    def test_information_schema_allowed(self):
        """Querying INFORMATION_SCHEMA is legitimate."""
        result = SecurityValidator.validate(
            "SELECT * FROM region-us.INFORMATION_SCHEMA.TABLES"
        )
        assert result["valid"] is True

    def test_semicolon_in_backtick_allowed(self):
        """Semicolons inside backtick identifiers should be allowed."""
        result = SecurityValidator.validate(
            "SELECT `col;name` FROM t"
        )
        assert result["valid"] is True

    def test_tab_in_backtick_column_allowed(self):
        """Tab character in backtick identifier should be allowed."""
        result = SecurityValidator.validate(
            "SELECT `col\tname` FROM t"
        )
        assert result["valid"] is True

    def test_keyword_in_table_name_allowed(self):
        """Table name containing a keyword substring (e.g., 'drop_log') is valid."""
        result = SecurityValidator.validate(
            "SELECT * FROM dataset.drop_log"
        )
        assert result["valid"] is True

    def test_multiple_comments_mixed(self):
        """Multiple comment styles all stripped before keyword scan."""
        result = SecurityValidator.validate(
            "SELECT * FROM t /* comment with DROP */ -- another DELETE\nWHERE id = 1"
        )
        assert result["valid"] is True
