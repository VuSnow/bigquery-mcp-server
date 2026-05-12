"""Tests for ConfigParser — YAML parsing, connection routing, guardrails layering."""
import os
import tempfile

import pytest
import yaml

from bigquery_mcp.utils.config_parser import ConfigParser


@pytest.fixture
def sample_config():
    """Return a full sample config dict."""
    return {
        "mcp": {"name": "bigquery-mcp", "version": "0.3.0"},
        "bq": {
            "default_connection": "prod-us",
            "connections": {
                "prod-us": {
                    "project": "my-prod-project",
                    "default_region": "US",
                    "datasets": ["analytics", "sales"],
                },
                "staging-eu": {
                    "project": "my-staging-project",
                    "default_region": "europe-west4",
                    "datasets": ["staging_analytics"],
                    "max_bytes_billed": 5_000_000_000,
                },
            },
        },
        "guardrails": {
            "read_only": True,
            "default_limit": 100,
            "max_limit": 1000,
            "max_bytes_billed": 10_737_418_240,
            "max_query_length": 10_000,
            "forbid_cross_connection": True,
            "rate_limit": {"max_calls": 100, "window_seconds": 3600},
        },
        "pii": [
            {"column": "email", "method": "hash"},
            {"column": "phone_number", "method": "redact"},
        ],
        "tables": [
            {
                "name": "analytics.fact_orders",
                "connection": "prod-us",
                "constraints": {"required_filters": ["order_date"]},
            },
        ],
        "blocked_tables": ["internal.*", "temp.*"],
    }


@pytest.fixture
def parser(sample_config, tmp_path):
    """Create a ConfigParser loaded with sample config."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(sample_config))

    # Reset singleton for fresh parse
    ConfigParser._instance = None
    ConfigParser._config = None

    old_env = os.environ.get("CONFIG_FILE_PATH")
    os.environ["CONFIG_FILE_PATH"] = str(config_file)

    # Force reload configs
    import importlib
    import bigquery_mcp.configs
    importlib.reload(bigquery_mcp.configs)

    p = ConfigParser()
    p._config = sample_config  # Direct inject to avoid env var issues

    yield p

    # Cleanup
    ConfigParser._instance = None
    ConfigParser._config = None
    if old_env is not None:
        os.environ["CONFIG_FILE_PATH"] = old_env
    elif "CONFIG_FILE_PATH" in os.environ:
        del os.environ["CONFIG_FILE_PATH"]


class TestConfigParserConnections:
    """Test connection config access."""

    def test_default_connection_name(self, parser):
        assert parser.get_default_connection_name() == "prod-us"

    def test_get_connections(self, parser):
        conns = parser.get_connections()
        assert "prod-us" in conns
        assert "staging-eu" in conns
        assert conns["prod-us"]["project"] == "my-prod-project"

    def test_get_connection_config(self, parser):
        cfg = parser.get_connection_config("staging-eu")
        assert cfg is not None
        assert cfg["project"] == "my-staging-project"

    def test_get_connection_config_not_found(self, parser):
        assert parser.get_connection_config("nonexistent") is None


class TestConfigParserRouting:
    """Test connection routing for datasets and tables."""

    def test_resolve_dataset_to_connection(self, parser):
        assert parser.resolve_connection_for_dataset("analytics") == "prod-us"
        assert parser.resolve_connection_for_dataset("staging_analytics") == "staging-eu"

    def test_resolve_unknown_dataset_falls_back(self, parser):
        assert parser.resolve_connection_for_dataset("unknown_ds") == "prod-us"

    def test_resolve_table_explicit_mapping(self, parser):
        # analytics.fact_orders has explicit connection: prod-us in tables[]
        assert parser.resolve_connection_for_table("analytics.fact_orders") == "prod-us"

    def test_resolve_table_by_dataset(self, parser):
        # staging_analytics.xxx should route to staging-eu
        assert parser.resolve_connection_for_table("staging_analytics.some_table") == "staging-eu"

    def test_resolve_table_unknown_falls_back(self, parser):
        assert parser.resolve_connection_for_table("unknown.table") == "prod-us"

    def test_resolve_three_part_table(self, parser):
        # project.dataset.table format
        assert parser.resolve_connection_for_table("project.analytics.orders") == "prod-us"


class TestConfigParserGuardrails:
    """Test guardrails config access and layering."""

    def test_global_guardrails(self, parser):
        g = parser.get_guardrails()
        assert g["read_only"] is True
        assert g["default_limit"] == 100
        assert g["max_limit"] == 1000

    def test_effective_guardrails_no_override(self, parser):
        g = parser.get_effective_guardrails("prod-us")
        assert g["max_bytes_billed"] == 10_737_418_240  # global value

    def test_effective_guardrails_with_override(self, parser):
        g = parser.get_effective_guardrails("staging-eu")
        assert g["max_bytes_billed"] == 5_000_000_000  # overridden

    def test_effective_guardrails_none_connection(self, parser):
        g = parser.get_effective_guardrails(None)
        assert g["max_bytes_billed"] == 10_737_418_240


class TestConfigParserPII:
    """Test PII rules."""

    def test_get_pii_rules(self, parser):
        rules = parser.get_pii_rules()
        assert len(rules) == 2
        assert rules[0]["column"] == "email"
        assert rules[1]["method"] == "redact"


class TestConfigParserTables:
    """Test table config and blocked tables."""

    def test_get_table_config(self, parser):
        cfg = parser.get_table_config("analytics.fact_orders")
        assert cfg is not None
        assert cfg["connection"] == "prod-us"

    def test_get_table_config_not_found(self, parser):
        assert parser.get_table_config("nonexistent.table") is None

    def test_blocked_tables(self, parser):
        assert parser.is_table_blocked("internal.secrets") is True
        assert parser.is_table_blocked("internal.users") is True
        assert parser.is_table_blocked("temp.scratch") is True
        assert parser.is_table_blocked("analytics.fact_orders") is False

    def test_get_blocked_tables(self, parser):
        patterns = parser.get_blocked_tables()
        assert "internal.*" in patterns
        assert "temp.*" in patterns


class TestConfigParserMCP:
    """Test MCP info."""

    def test_mcp_info(self, parser):
        info = parser.get_mcp_info()
        assert info["name"] == "bigquery-mcp"
        assert info["version"] == "0.3.0"
