"""YAML config parser — loads and caches config.yaml for guardrails, blocked tables, PII."""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from bigquery_mcp.configs import configs, ROOT_DIR

logger = logging.getLogger(__name__)


class ConfigParser:
    """Singleton YAML configuration parser."""

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

    def get_settings(self) -> Dict[str, Any]:
        """Get settings section."""
        return self._config.get("settings", {})

    def get_tables(self) -> List[Dict[str, Any]]:
        """Get all table constraint definitions from config."""
        return self._config.get("tables", [])

    def get_table_config(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Get constraints config for a specific table by name."""
        for table in self.get_tables():
            if table.get("name") == table_name:
                return table
        return None

    def get_guardrails(self) -> Dict[str, Any]:
        """Get guardrails configuration."""
        return self._config.get("guardrails", {})

    def get_pii_masking(self) -> List[Dict[str, Any]]:
        """Get PII masking configuration."""
        return self._config.get("pii_masking", [])

    def get_blocked_tables(self) -> List[str]:
        """Get blocked tables list (supports glob patterns)."""
        return self._config.get("blocked_tables", [])

    def is_table_blocked(self, table_name: str) -> bool:
        """Check if a table matches any blocked pattern."""
        for pattern in self.get_blocked_tables():
            if fnmatch.fnmatch(table_name, pattern):
                return True
        return False

    def get_whitelisted_table_names(self) -> List[str]:
        """Get list of table names defined in YAML (for yaml_only mode)."""
        return [t.get("name") for t in self.get_tables() if t.get("name")]


# Singleton instance
config_parser = ConfigParser()
