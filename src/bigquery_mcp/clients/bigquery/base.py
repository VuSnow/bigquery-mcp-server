"""Base BigQuery client — handles connection and credentials."""
from __future__ import annotations

import logging
from typing import Optional

from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class BaseBigQueryClient:
    """Holds the shared BigQuery client instance."""

    def __init__(
        self,
        project_id: str,
        location: str = "US",
        key_file: Optional[str] = None,
    ) -> None:
        credentials: Optional[service_account.Credentials] = None
        if key_file:
            credentials = service_account.Credentials.from_service_account_file(
                key_file,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            logger.info("Loaded service account credentials from: %s", key_file)
        else:
            logger.info("Using application default credentials")

        self._client = bigquery.Client(
            credentials=credentials,
            project=project_id,
            location=location,
        )
        self._project_id = project_id
        self._location = location
        logger.info(
            "BigQuery client initialized — project=%s, location=%s",
            project_id,
            location,
        )

    @property
    def project_id(self) -> str:
        return self._project_id

    @property
    def location(self) -> str:
        return self._location

    def ping(self) -> bool:
        """Verify connectivity by running a trivial query."""
        query = "SELECT 1"
        result = self._client.query(query).result()
        return list(result)[0][0] == 1

    def close(self) -> None:
        """Close the underlying client."""
        self._client.close()
