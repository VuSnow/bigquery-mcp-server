"""Metadata operations: list datasets, list tables, get table info, get table schema."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseBigQueryClient

logger = logging.getLogger(__name__)


class MetadataClient(BaseBigQueryClient):
    """Mixin for dataset/table metadata operations via BigQuery API."""

    def list_datasets(self) -> List[Dict[str, Any]]:
        """List all datasets in the project."""
        datasets = list(self._client.list_datasets())
        return [
            {
                "dataset_id": ds.dataset_id,
                "project": ds.project,
                "full_id": f"{ds.project}.{ds.dataset_id}",
            }
            for ds in datasets
        ]

    def list_tables(self, dataset: str) -> List[Dict[str, Any]]:
        """List all tables in a dataset."""
        tables = list(self._client.list_tables(dataset))
        return [
            {
                "table_id": t.table_id,
                "dataset_id": dataset,
                "full_id": f"{t.project}.{dataset}.{t.table_id}",
                "table_type": t.table_type,
            }
            for t in tables
        ]

    def get_table(self, table_ref: str) -> Dict[str, Any]:
        """Get full table metadata from BigQuery API.

        Args:
            table_ref: Fully qualified table name (project.dataset.table or dataset.table).
        """
        table = self._client.get_table(table_ref)
        return {
            "table_id": table.table_id,
            "dataset_id": table.dataset_id,
            "project": table.project,
            "full_id": f"{table.project}.{table.dataset_id}.{table.table_id}",
            "table_type": table.table_type,
            "description": table.description,
            "num_rows": table.num_rows,
            "num_bytes": table.num_bytes,
            "created": table.created.isoformat() if table.created else None,
            "modified": table.modified.isoformat() if table.modified else None,
            "labels": dict(table.labels) if table.labels else {},
            "partitioning_type": (
                table.time_partitioning.type_ if table.time_partitioning else None
            ),
            "partitioning_field": (
                table.time_partitioning.field if table.time_partitioning else None
            ),
            "clustering_fields": table.clustering_fields,
            "schema": [
                {
                    "name": field.name,
                    "type": field.field_type,
                    "mode": field.mode,
                    "description": field.description,
                }
                for field in table.schema
            ],
        }

    def get_table_schema(self, table_ref: str) -> List[Dict[str, Any]]:
        """Get only the schema (columns) for a table.

        Args:
            table_ref: Fully qualified table name (project.dataset.table or dataset.table).
        """
        table = self._client.get_table(table_ref)
        return [
            {
                "name": field.name,
                "type": field.field_type,
                "mode": field.mode,
                "description": field.description,
            }
            for field in table.schema
        ]
