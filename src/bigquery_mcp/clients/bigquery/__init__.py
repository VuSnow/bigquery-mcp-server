"""BigQuery client — combines all operation types via mixin inheritance."""
from .metadata import MetadataClient
from .discovery import DiscoveryClient
from .query import QueryClient
from .ddl import DDLClient

__all__ = ["BigQueryClient"]


class BigQueryClient(MetadataClient, DiscoveryClient, QueryClient, DDLClient):
    """Full BigQuery client — combines all operation types via mixin inheritance."""
    pass
