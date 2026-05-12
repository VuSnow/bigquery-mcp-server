"""Tests for ConnectionManager — lazy init, routing, status."""
from unittest.mock import MagicMock, patch

import pytest

from bigquery_mcp.services.connection_manager import (
    ConnectionManager,
    ConnectionState,
)


@pytest.fixture
def manager():
    return ConnectionManager()


@pytest.fixture
def mock_config():
    """Mock config_parser with two connections."""
    with patch("bigquery_mcp.services.connection_manager.config_parser") as mock_cp:
        mock_cp.get_connection_config.side_effect = lambda name: {
            "prod-us": {"project": "my-prod", "default_region": "US"},
            "staging-eu": {"project": "my-staging", "default_region": "europe-west4"},
        }.get(name)
        mock_cp.get_connections.return_value = {
            "prod-us": {"project": "my-prod"},
            "staging-eu": {"project": "my-staging"},
        }
        mock_cp.get_default_connection_name.return_value = "prod-us"
        yield mock_cp


class TestConnectionManagerConnect:
    """Test connection lifecycle."""

    @patch("bigquery_mcp.services.connection_manager.BigQueryClient")
    def test_connect_creates_client(self, MockClient, manager):
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {
                "project": "my-project",
                "default_region": "US",
            }
            client = manager.connect("prod-us")

        assert client is mock_client
        mock_client.ping.assert_called_once()

    @patch("bigquery_mcp.services.connection_manager.BigQueryClient")
    def test_connect_reuses_client(self, MockClient, manager):
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {
                "project": "my-project",
                "default_region": "US",
            }
            c1 = manager.connect("prod-us")
            c2 = manager.connect("prod-us")

        assert c1 is c2
        assert MockClient.call_count == 1  # only created once

    def test_connect_unknown_raises(self, manager):
        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = None
            mock_cp.get_connections.return_value = {}

            with pytest.raises(ConnectionError, match="not found"):
                manager.connect("nonexistent")

    @patch("bigquery_mcp.services.connection_manager.BigQueryClient")
    def test_connect_failure_sets_error(self, MockClient, manager):
        MockClient.return_value.ping.side_effect = Exception("Auth failed")

        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {
                "project": "my-project",
            }
            with pytest.raises(ConnectionError, match="Auth failed"):
                manager.connect("prod-us")


class TestConnectionManagerGetClient:
    """Test lazy-init via get_client."""

    @patch("bigquery_mcp.services.connection_manager.BigQueryClient")
    def test_get_client_lazy_init(self, MockClient, manager):
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {
                "project": "my-project",
                "default_region": "US",
            }
            client = manager.get_client("prod-us")
        assert client is mock_client


class TestConnectionManagerDisconnect:
    """Test disconnect behavior."""

    @patch("bigquery_mcp.services.connection_manager.BigQueryClient")
    def test_disconnect(self, MockClient, manager):
        mock_client = MagicMock()
        MockClient.return_value = mock_client

        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {
                "project": "my-project",
            }
            manager.connect("prod-us")
            manager.disconnect("prod-us")

        mock_client.close.assert_called_once()

    @patch("bigquery_mcp.services.connection_manager.BigQueryClient")
    def test_disconnect_all(self, MockClient, manager):
        mock_client1 = MagicMock()
        mock_client2 = MagicMock()
        MockClient.side_effect = [mock_client1, mock_client2]

        with patch(
            "bigquery_mcp.utils.config_parser.config_parser"
        ) as mock_cp:
            mock_cp.get_connection_config.return_value = {
                "project": "my-project",
            }
            manager.connect("conn1")
            manager.connect("conn2")
            manager.disconnect_all()

        mock_client1.close.assert_called_once()
        mock_client2.close.assert_called_once()
