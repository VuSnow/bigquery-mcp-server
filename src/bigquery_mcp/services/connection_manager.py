"""Manages multiple BigQuery connections (lazy-init per connection name)."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Dict, Optional

from bigquery_mcp.clients.bigquery import BigQueryClient

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionManager:
    """Manages named BigQuery connections. Lazy-init on first use."""

    def __init__(self) -> None:
        self._clients: Dict[str, BigQueryClient] = {}
        self._states: Dict[str, ConnectionState] = {}
        self._errors: Dict[str, str] = {}

    def connect(self, connection_name: str) -> BigQueryClient:
        """Connect to a named BigQuery connection. Uses config_parser for settings.

        Args:
            connection_name: Connection name as defined in YAML bq.connections.
        """
        from bigquery_mcp.utils.config_parser import config_parser

        if connection_name in self._clients:
            return self._clients[connection_name]

        conn_config = config_parser.get_connection_config(connection_name)
        if not conn_config:
            raise ConnectionError(
                f"Connection '{connection_name}' not found in config. "
                f"Available: {list(config_parser.get_connections().keys())}"
            )

        logger.info(
            "[connection] Connecting '%s' — project=%s, region=%s",
            connection_name,
            conn_config.get("project"),
            conn_config.get("default_region", "US"),
        )
        self._states[connection_name] = ConnectionState.CONNECTING
        self._errors.pop(connection_name, None)

        try:
            client = BigQueryClient(
                project_id=conn_config["project"],
                location=conn_config.get("default_region", "US"),
                key_file=conn_config.get("key_file"),
            )
            client.ping()
            self._clients[connection_name] = client
            self._states[connection_name] = ConnectionState.CONNECTED
            logger.info("[connection] '%s' connected successfully", connection_name)
            return client
        except Exception as e:
            self._states[connection_name] = ConnectionState.ERROR
            self._errors[connection_name] = str(e)
            logger.error("[connection] '%s' failed: %s", connection_name, e, exc_info=True)
            raise ConnectionError(f"Failed to connect '{connection_name}': {e}") from e

    def get_client(self, connection_name: str) -> BigQueryClient:
        """Get or create a client for the named connection (lazy-init)."""
        if connection_name in self._clients:
            return self._clients[connection_name]
        return self.connect(connection_name)

    def get_default_client(self) -> BigQueryClient:
        """Get client for the default connection."""
        from bigquery_mcp.utils.config_parser import config_parser
        return self.get_client(config_parser.get_default_connection_name())

    def disconnect(self, connection_name: str) -> None:
        """Disconnect a specific connection."""
        if connection_name in self._clients:
            self._clients[connection_name].close()
            del self._clients[connection_name]
        self._states[connection_name] = ConnectionState.DISCONNECTED
        self._errors.pop(connection_name, None)
        logger.info("[connection] '%s' disconnected", connection_name)

    def disconnect_all(self) -> None:
        """Disconnect all connections."""
        for name in list(self._clients.keys()):
            self.disconnect(name)

    def get_status(self) -> Dict[str, str]:
        """Get state of all known connections."""
        from bigquery_mcp.utils.config_parser import config_parser
        status = {}
        for name in config_parser.get_connections():
            state = self._states.get(name, ConnectionState.DISCONNECTED)
            status[name] = state.value
        return status

    @property
    def connected_count(self) -> int:
        return len(self._clients)


# Singleton — shared across all services
connection_manager = ConnectionManager()
