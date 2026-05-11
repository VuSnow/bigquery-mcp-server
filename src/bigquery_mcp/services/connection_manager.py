"""Manages BigQuery connection lifecycle and state."""
from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from bigquery_mcp.clients.bigquery import BigQueryClient
from bigquery_mcp.configs import configs

logger = logging.getLogger(__name__)


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionManager:
    """Manages BigQuery connection state. Provides client access to services."""

    def __init__(self) -> None:
        self._state = ConnectionState.DISCONNECTED
        self._client: Optional[BigQueryClient] = None
        self._error: Optional[str] = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def error(self) -> Optional[str]:
        return self._error

    def connect(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        key_file: Optional[str] = None,
    ) -> None:
        """Connect to BigQuery. Uses config values if not provided."""
        resolved_project = project_id or configs.project_id
        resolved_location = location or configs.location
        resolved_key_file = key_file or configs.key_file

        logger.info(
            "[connection] Connecting to BigQuery — project=%s, location=%s",
            resolved_project,
            resolved_location,
        )
        self._state = ConnectionState.CONNECTING
        self._error = None

        try:
            self._client = BigQueryClient(
                project_id=resolved_project,
                location=resolved_location,
                key_file=resolved_key_file,
            )
            self._client.ping()
            self._state = ConnectionState.CONNECTED
            logger.info("[connection] Connected successfully to project=%s", resolved_project)
        except Exception as e:
            self._state = ConnectionState.ERROR
            self._error = str(e)
            self._client = None
            logger.error("[connection] Failed to connect: %s", e, exc_info=True)
            raise ConnectionError(f"Failed to connect to BigQuery: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from BigQuery."""
        logger.info("[connection] Disconnecting (current state=%s)", self._state.value)
        if self._client:
            self._client.close()
        self._client = None
        self._state = ConnectionState.DISCONNECTED
        self._error = None
        logger.info("[connection] Disconnected")

    def get_client(self) -> BigQueryClient:
        """Get the active BigQuery client. Raises if not connected."""
        if self._state != ConnectionState.CONNECTED or not self._client:
            logger.error("[connection] get_client() called but state=%s", self._state.value)
            raise ConnectionError(
                f"BigQuery is not connected (state: {self._state.value}). "
                "Connection will be auto-initiated on first tool call."
            )
        return self._client


# Singleton — shared across all services and tools
connection_manager = ConnectionManager()
