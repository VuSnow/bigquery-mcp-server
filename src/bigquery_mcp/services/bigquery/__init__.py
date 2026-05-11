"""BigQuery service — combines all operation mixins."""
from .metadata import MetadataService
from .discovery import DiscoveryService
from .query import QueryService


class BigQueryService(MetadataService, DiscoveryService, QueryService):
    """Full BigQuery service. Combines all operation mixins."""
    pass


# Singleton — shared across all tools
bigquery_service = BigQueryService()
