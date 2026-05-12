"""MCP tools for BigQuery query operations.

Thin wrappers around BigQueryService — format output for LLM consumption.
"""
import json
from typing import Optional

from bigquery_mcp.app import mcp
from bigquery_mcp.services.bigquery import bigquery_service


@mcp.tool()
def dry_run_query(query: str, connection: Optional[str] = None) -> str:
    """Validate a SQL query and estimate bytes/cost without executing it.

    Always dry-run before executing expensive queries.

    Args:
        query: SQL query to validate (SELECT/WITH only).
        connection: Optional connection name. Uses default if omitted.

    Returns:
        Validation result with estimated bytes processed.
    """
    try:
        result = bigquery_service.dry_run_query(query, connection=connection)
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    est = result["estimation"]
    bytes_processed = est.get("total_bytes_processed", 0)

    # Human-readable size
    if bytes_processed >= 1_073_741_824:
        size_str = f"{bytes_processed / 1_073_741_824:.2f} GiB"
    elif bytes_processed >= 1_048_576:
        size_str = f"{bytes_processed / 1_048_576:.2f} MiB"
    elif bytes_processed >= 1024:
        size_str = f"{bytes_processed / 1024:.2f} KiB"
    else:
        size_str = f"{bytes_processed} bytes"

    lines = [
        "Query is valid.",
        f"  Connection: {result['connection']}",
        f"  Estimated bytes: {size_str} ({bytes_processed:,} bytes)",
    ]

    if est.get("referenced_tables"):
        tables = [f"{t.get('dataset_id', '?')}.{t.get('table_id', '?')}" for t in est["referenced_tables"]]
        lines.append(f"  Referenced tables: {', '.join(tables)}")

    if est.get("schema"):
        cols = [f"{c['name']} ({c['type']})" for c in est["schema"][:20]]
        lines.append(f"  Output columns: {', '.join(cols)}")
        if len(est["schema"]) > 20:
            lines.append(f"  ... and {len(est['schema']) - 20} more columns")

    return "\n".join(lines)


@mcp.tool()
def execute_query(query: str, connection: Optional[str] = None) -> str:
    """Execute a read-only SQL query against BigQuery with full guardrails.

    Pipeline: rate limit → security validation → query rewrite (auto LIMIT) → execute → PII masking → audit.

    Args:
        query: SQL query to execute (SELECT/WITH only).
        connection: Optional connection name. Auto-routes if omitted.

    Returns:
        Query results as JSON rows with metadata.
    """
    try:
        result = bigquery_service.execute_query(query, connection=connection)
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        msg = f"Error: {result.get('message', 'Unknown error')}"
        if result.get("stage"):
            msg += f" (stage: {result['stage']})"
        return msg

    lines = [f"Query executed successfully on '{result['connection']}'. {result['count']} rows returned."]

    if result.get("modifications"):
        lines.append(f"  Modifications: {', '.join(result['modifications'])}")
    if result.get("masked_fields"):
        lines.append(f"  PII masked: {', '.join(result['masked_fields'])}")

    lines.append("")

    # Format rows as JSON for LLM consumption
    rows_json = json.dumps(result["rows"], indent=2, default=str)
    lines.append(rows_json)

    return "\n".join(lines)


@mcp.tool()
def explain_query_error(error_message: str, query: str) -> str:
    """Analyze a BigQuery error message and suggest fixes.

    Use this when a query fails to get actionable suggestions for the next retry.

    Args:
        error_message: The error message from a failed query execution.
        query: The SQL query that produced the error.

    Returns:
        Analysis of the error with suggested fixes.
    """
    try:
        result = bigquery_service.explain_query_error(error_message, query)
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    lines = [
        f"Error: {result['error_message']}",
        "",
        "Suggestions:",
    ]
    for i, suggestion in enumerate(result["suggestions"], 1):
        lines.append(f"  {i}. {suggestion}")

    return "\n".join(lines)


@mcp.tool()
def get_status() -> str:
    """Get server health, connection status, and guardrails configuration.

    Use this to check which connections are active, current rate limit usage,
    and guardrail settings before executing queries.

    Returns:
        Server status with connections, guardrails, and rate limit info.
    """
    try:
        result = bigquery_service.get_status()
    except Exception as e:
        return f"Error: {e}"

    if result["status"] != "ok":
        return f"Error: {result.get('message', 'Unknown error')}"

    lines = ["Server Status:"]
    lines.append(f"  Default connection: {result['default_connection']}")

    # Connections
    lines.append("")
    lines.append("Connections:")
    connections = result.get("connections", {})
    for name, info in connections.items():
        status = info.get("status", "unknown")
        project = info.get("project", "?")
        lines.append(f"  - {name}: {status} (project: {project})")

    # Guardrails
    lines.append("")
    lines.append("Guardrails:")
    g = result.get("guardrails", {})
    lines.append(f"  Read-only: {g.get('read_only', True)}")
    lines.append(f"  Default LIMIT: {g.get('default_limit', 100)}")
    lines.append(f"  Max LIMIT: {g.get('max_limit', 1000)}")
    if g.get("max_bytes_billed"):
        max_gb = g["max_bytes_billed"] / 1_073_741_824
        lines.append(f"  Max bytes billed: {max_gb:.1f} GiB")
    lines.append(f"  Max query length: {g.get('max_query_length', 10_000):,}")
    lines.append(f"  Cross-connection blocked: {g.get('forbid_cross_connection', False)}")

    # Rate limit
    rl = g.get("rate_limit", {})
    if rl:
        lines.append(f"  Rate limit: {rl.get('used', 0)}/{rl.get('max_calls', '?')} "
                      f"(window: {rl.get('window_seconds', '?')}s)")

    # PII / blocked
    if result.get("pii_rules_count"):
        lines.append(f"  PII rules: {result['pii_rules_count']}")
    if result.get("blocked_tables"):
        lines.append(f"  Blocked patterns: {', '.join(result['blocked_tables'])}")

    return "\n".join(lines)
