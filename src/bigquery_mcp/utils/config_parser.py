"""YAML config parser — single source of truth for multi-connection BQ MCP server."""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from bigquery_mcp.configs import configs, ROOT_DIR

logger = logging.getLogger(__name__)


class ConfigParser:
    """Singleton YAML configuration parser with multi-connection support."""

    _instance: Optional["ConfigParser"] = None
    _config: Optional[Dict[str, Any]] = None

    def __new__(cls) -> "ConfigParser":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if ConfigParser._config is None:
            ConfigParser._config = self._load_config()
            logger.info("YAML configuration loaded successfully")

    def _load_config(self) -> Dict[str, Any]:
        """Load YAML config from file path."""
        config_path = configs.config_file_path
        if config_path:
            path = Path(config_path)
        else:
            path = ROOT_DIR / "config.yaml"

        if not path.exists():
            logger.warning("Config file not found at %s — using empty config", path)
            return {}

        with open(path, "r") as f:
            config = yaml.safe_load(f) or {}

        logger.info("Loaded config from %s", path)
        return config

    # ─── MCP info ─────────────────────────────────────────────────────

    def get_mcp_info(self) -> Dict[str, Any]:
        """Get MCP server metadata (name, version)."""
        return self._config.get("mcp", {})

    # ─── BigQuery connections ─────────────────────────────────────────

    def get_default_connection_name(self) -> str:
        """Get the default connection name."""
        bq = self._config.get("bq", {})
        return bq.get("default_connection", "default")

    def get_connections(self) -> Dict[str, Dict[str, Any]]:
        """Get all connection configs as {name: config}."""
        bq = self._config.get("bq", {})
        return bq.get("connections", {})

    def get_connection_config(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific connection config by name."""
        return self.get_connections().get(name)

    def get_default_connection_config(self) -> Optional[Dict[str, Any]]:
        """Get the default connection config."""
        return self.get_connection_config(self.get_default_connection_name())

    def resolve_connection_for_dataset(self, dataset: str) -> str:
        """Resolve which connection owns a dataset.

        Resolution order:
        1. Connection whose `datasets` list contains the dataset
        2. Default connection
        """
        for conn_name, conn_config in self.get_connections().items():
            datasets = conn_config.get("datasets", [])
            if dataset in datasets:
                return conn_name
        return self.get_default_connection_name()

    def resolve_connection_for_table(self, table_name: str) -> str:
        """Resolve which connection a table belongs to.

        Resolution order:
        1. tables[].connection explicit mapping
        2. Dataset match via bq.connections[].datasets
        3. Default connection
        """
        # Check explicit table → connection mapping
        table_config = self.get_table_config(table_name)
        if table_config and table_config.get("connection"):
            return table_config["connection"]

        # Extract dataset from table_name (dataset.table or project.dataset.table)
        parts = table_name.split(".")
        if len(parts) >= 2:
            dataset = parts[-2] if len(parts) == 2 else parts[1]
            return self.resolve_connection_for_dataset(dataset)

        return self.get_default_connection_name()

    # ─── Guardrails ───────────────────────────────────────────────────

    def get_guardrails(self) -> Dict[str, Any]:
        """Get global guardrails configuration."""
        return self._config.get("guardrails", {})

    def get_effective_guardrails(self, connection_name: Optional[str] = None) -> Dict[str, Any]:
        """Get guardrails with per-connection overrides applied.

        Layered: global guardrails → connection-level overrides.
        """
        guardrails = dict(self.get_guardrails())  # copy global

        if connection_name:
            conn_config = self.get_connection_config(connection_name)
            if conn_config:
                # Per-connection overrides
                if "max_bytes_billed" in conn_config:
                    guardrails["max_bytes_billed"] = conn_config["max_bytes_billed"]
                if "default_limit" in conn_config:
                    guardrails["default_limit"] = conn_config["default_limit"]
                if "max_limit" in conn_config:
                    guardrails["max_limit"] = conn_config["max_limit"]

        return guardrails

    # ─── PII masking ──────────────────────────────────────────────────

    def get_pii_rules(self) -> List[Dict[str, Any]]:
        """Get PII masking rules."""
        return self._config.get("pii", [])

    # ─── Tables ───────────────────────────────────────────────────────

    def get_tables(self) -> List[Dict[str, Any]]:
        """Get all table definitions from config."""
        return self._config.get("tables", [])

    def get_table_config(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get config for a specific table by name."""
        for table in self.get_tables():
            if table.get("name") == table_name:
                return table
        return None

    # ─── Blocked tables ───────────────────────────────────────────────

    def get_blocked_tables(self) -> List[str]:
        """Get blocked tables list (supports glob patterns)."""
        return self._config.get("blocked_tables", [])

    def is_table_blocked(self, table_name: str) -> bool:
        """Check if a table matches any blocked pattern."""
        for pattern in self.get_blocked_tables():
            if fnmatch.fnmatch(table_name, pattern):
                return True
        return False


# Singleton instance
config_parser = ConfigParser()
