"""MCP tools for BigQuery metadata operations.

Thin wrappers around BigQueryService — format output for LLM consumption.
"""
from typing import Optional

from bigquery_mcp.app import mcp
from bigquery_mcp.services.bigquery import bigquery_service


@mcp.tool()
def list_datasets(connection: Optional[str] = None) -> str:
    """List all accessible BigQuery datasets.

    Args:
        connection: Optional connection name. If omitted, uses default connection.

    Returns:
        Formatted list of datasets with their IDs and metadata.
    """
    try:
        result = bigquery_service.list_datasets(connection=connection)
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    if not result["datasets"]:
        return f"No datasets found on connection '{result['connection']}'."

    lines = [f"Datasets on '{result['connection']}' ({result['count']}):"]
    for ds in result["datasets"]:
        line = f"  - {ds['dataset_id']}"
        if ds.get("location"):
            line += f"  (location: {ds['location']})"
        lines.append(line)
    return "\n".join(lines)


@mcp.tool()
def list_tables(dataset: str, connection: Optional[str] = None) -> str:
    """List all tables in a BigQuery dataset.

    Args:
        dataset: Dataset ID (e.g., 'analytics').
        connection: Optional connection name. Auto-routes if omitted.

    Returns:
        Formatted list of tables with type and row count.
    """
    try:
        result = bigquery_service.list_tables(dataset, connection=connection)
    except (ValueError, PermissionError) as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    if not result["tables"]:
        return f"No tables found in '{result['dataset']}' (connection: {result['connection']})."

    lines = [f"Tables in '{result['dataset']}' via '{result['connection']}' ({result['count']}):"]
    for t in result["tables"]:
        parts = [f"  - {t['table_id']}"]
        if t.get("table_type"):
            parts.append(f"[{t['table_type']}]")
        if t.get("num_rows") is not None:
            parts.append(f"({t['num_rows']:,} rows)")
        lines.append(" ".join(parts))
    return "\n".join(lines)


@mcp.tool()
def get_table_schema(table_name: str, connection: Optional[str] = None) -> str:
    """Get column definitions and metadata for a BigQuery table.

    Args:
        table_name: Fully qualified table name (dataset.table or project.dataset.table).
        connection: Optional connection name. Auto-routes based on table/dataset.

    Returns:
        Column schema with types, modes, partitioning, and clustering info.
    """
    try:
        result = bigquery_service.get_table_schema(table_name, connection=connection)
    except (ValueError, PermissionError) as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    lines = [f"Schema for '{result['table']}' (connection: {result['connection']}, {result['column_count']} columns):"]

    if result.get("num_rows") is not None:
        lines.append(f"  Total rows: {result['num_rows']:,}")
    if result.get("partitioning"):
        tp = result["partitioning"]
        lines.append(f"  Partitioned by: {tp.get('field', 'ingestion time')} ({tp.get('type', 'DAY')})")
    if result.get("clustering_fields"):
        lines.append(f"  Clustered by: {', '.join(result['clustering_fields'])}")

    lines.append("")
    lines.append("Columns:")
    for col in result["columns"]:
        mode = f" ({col['mode']})" if col.get("mode") and col["mode"] != "NULLABLE" else ""
        desc = f"  -- {col['description']}" if col.get("description") else ""
        lines.append(f"  - {col['name']}: {col['type']}{mode}{desc}")

    return "\n".join(lines)


@mcp.tool()
def describe_table(table_name: str, connection: Optional[str] = None) -> str:
    """Get the DDL (CREATE TABLE statement) for a BigQuery table.

    Args:
        table_name: Fully qualified table name (dataset.table or project.dataset.table).
        connection: Optional connection name. Auto-routes based on table/dataset.

    Returns:
        The CREATE TABLE DDL statement.
    """
    try:
        result = bigquery_service.describe_table(table_name, connection=connection)
    except (ValueError, PermissionError) as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    return result["ddl"]


@mcp.tool()
def get_column_values(
    table_name: str,
    column: str,
    limit: int = 50,
    connection: Optional[str] = None,
) -> str:
    """Get distinct values for a column in a BigQuery table.

    Useful for understanding categorical columns, building WHERE filters, or exploring data.

    Args:
        table_name: Fully qualified table name (dataset.table).
        column: Column name to get distinct values for.
        limit: Maximum number of distinct values to return (1-200, default 50).
        connection: Optional connection name.

    Returns:
        List of distinct values with their counts.
    """
    try:
        result = bigquery_service.get_column_values(
            table_name, column, limit=limit, connection=connection,
        )
    except (ValueError, PermissionError) as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    if not result["values"]:
        return f"No values found for column '{result['column']}' in '{result['table']}'."

    lines = [f"Distinct values for '{result['column']}' in '{result['table']}' ({result['count']}):"]
    for v in result["values"]:
        lines.append(f"  - {v}")
    return "\n".join(lines)
