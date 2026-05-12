"""BigQuery client — combines all operation types via mixin inheritance."""
from .metadata import MetadataClient
from .query import QueryClient
from .ddl import DDLClient

__all__ = ["BigQueryClient"]


class BigQueryClient(MetadataClient, QueryClient, DDLClient):
    """Full BigQuery client — combines all operation types via mixin inheritance."""
    pass
