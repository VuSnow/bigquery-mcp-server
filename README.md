# bigquery-mcp-server

BigQuery MCP server providing dataset discovery, schema inspection, metadata, dry-run validation, and query execution tools for Text2SQL agents and AI data workflows.

## Overview

`bigquery-mcp-server` is a Python MCP server built with [FastMCP](https://github.com/jlowin/fastmcp) that exposes Google BigQuery operations as well-defined MCP tools.

Instead of letting an agent interact with BigQuery directly, this server provides a controlled interface with security guardrails — query validation, rate limiting, PII masking, table whitelisting, and audit logging.

Designed as the **data layer** for Text2SQL agents (like Uber's QueryGPT), where the agent handles NL→SQL generation and this server handles safe BigQuery access.

## Features

- Connect to BigQuery via service account or application default credentials
- Expose BigQuery operations as FastMCP tools
- List datasets and tables
- Inspect table schema, metadata, and DDL
- Dry-run query validation (syntax + cost estimation)
- Execute read-only queries with full guardrails
- YAML-based configuration for table whitelist, guardrails, and PII masking
- Rate limiting and audit logging
- Multi-project/multi-dataset support via connection aliases
- Read-only mode by default (SELECT/WITH/SHOW/DESCRIBE/EXPLAIN only)

## Project Structure

```txt
bigquery-mcp-server/
├── pyproject.toml
├── pytest.ini
├── README.md
├── .env.example
├── config.sample.yaml
├── src/
│   └── bigquery_mcp/
│       ├── __init__.py
│       ├── server.py                       # FastMCP instance, tool registration
│       ├── configs.py                      # Config via pydantic-settings (env vars)
│       │
│       ├── clients/
│       │   ├── __init__.py
│       │   └── bigquery/                   # BigQuery client (google-cloud-bigquery)
│       │       ├── __init__.py             # BigQueryClient (mixin composition)
│       │       ├── base.py                 # BaseBigQueryClient (connection, project, credentials)
│       │       ├── metadata.py             # list_datasets, list_tables, get_table_info, get_table_schema
│       │       ├── discovery.py            # search_tables, get_join_rules, get_column_values, get_example_queries
│       │       ├── query.py                # execute_query, dry_run_query, estimate_cost
│       │       └── ddl.py                  # describe_table (DDL retrieval)
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── connection_manager.py       # Connection state machine (singleton, multi-project)
│       │   └── bigquery/                   # BigQuery service layer (mixin-based)
│       │       ├── __init__.py             # BigQueryService (composed) + singleton
│       │       ├── base.py                 # BaseService (ensure_connected, validation helpers)
│       │       ├── metadata.py             # MetadataService (list, schema, info, DDL)
│       │       ├── discovery.py            # DiscoveryService (search, join rules, column values, examples)
│       │       ├── query.py                # QueryService (execute, dry_run, explain_error)
│       │       └── guardrails/             # Security & guardrails sub-package
│       │           ├── __init__.py
│       │           ├── security_validator.py   # Forbidden keywords, injection patterns, query length
│       │           ├── yaml_validator.py       # Table whitelist, partition filters, date range, operations
│       │           ├── query_rewriter.py       # Auto LIMIT, table normalization, date filters
│       │           ├── pii_masker.py           # Hash/redact PII fields in results
│       │           ├── rate_limiter.py         # Per-client rate limiting
│       │           └── audit_logger.py         # Security audit logging
│       │
│       ├── tools/                          # Tool definitions (thin layer, delegates to services)
│       │   ├── __init__.py
│       │   └── bigquery/                   # BigQuery tools package
│       │       ├── __init__.py             # Re-exports all tools + side-effect imports
│       │       ├── metadata.py             # list_datasets, list_tables, get_table_info, get_table_schema, describe_table
│       │       ├── discovery.py            # search_tables, get_join_rules, get_column_values, get_example_queries
│       │       └── query.py                # execute_query, dry_run_query, explain_query_error, get_security_status
│       │
│       └── utils/
│           ├── __init__.py
│           ├── config_parser.py            # YAML config loader (singleton, multi-file merge)
│           └── logging.py                  # Structured logging setup
│
└── test/
    ├── conftest.py
    └── units/
        ├── services/
        │   ├── test_base_service.py
        │   ├── test_connection_manager.py
        │   ├── test_metadata_service.py
        │   ├── test_query_service.py
        │   └── guardrails/
        │       ├── test_security_validator.py
        │       ├── test_yaml_validator.py
        │       ├── test_query_rewriter.py
        │       ├── test_pii_masker.py
        │       └── test_rate_limiter.py
        └── tools/
            ├── test_metadata_tools.py
            ├── test_discovery_tools.py
            └── test_query_tools.py
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Tools Layer (tools/)                                   │
│  - Defines MCP tool name, description, input schema     │
│  - Formats output for LLM consumption                  │
│  - Try/except top-level, returns user-friendly messages │
├─────────────────────────────────────────────────────────┤
│  Services Layer (services/bigquery/)                    │
│  - Connection management (ensure_connected)             │
│  - Input validation & sanitization                      │
│  - Guardrails pipeline (validate → rewrite → execute)  │
│  - Rate limiting & audit logging                        │
│  - PII masking on results                              │
│  - Read-only mode enforcement                           │
├─────────────────────────────────────────────────────────┤
│  Clients Layer (clients/bigquery/)                      │
│  - Pure google-cloud-bigquery calls                     │
│  - No business logic, no error handling                 │
│  - Translates Python params → BigQuery API operations   │
└─────────────────────────────────────────────────────────┘
            │
            ▼
       Google BigQuery API
```

### Key Design Decisions

- **3-Layer Separation**: Tools define interface, services own logic/security, clients are pure API wrappers.
- **Guardrails Pipeline**: Every query goes through: rate limit → security validation → YAML guardrails → rewrite → execute → PII mask → audit log.
- **YAML-Driven Config**: Table whitelist, guardrails, PII fields, rate limits all defined in `config.yaml`. No code changes needed to add tables or adjust limits.
- **Mixin Composition**: Client and service layers use base + mixins → composed class (same pattern as mongodb-mcp-server).
- **Singleton Services**: `connection_manager` and `bigquery_service` are module-level singletons shared across all tools.
- **Multi-Project Support**: Connection aliases allow querying multiple GCP projects from a single server instance.

## Tools

| # | Tool | Description | Layer |
|---|------|-------------|-------|
| 1 | `list_datasets` | List available BigQuery datasets | metadata |
| 2 | `list_tables` | List tables in a dataset (with tag/purpose filter) | metadata |
| 3 | `get_table_info` | Detailed metadata: purpose, tags, constraints, allowed ops | metadata |
| 4 | `get_table_schema` | Column definitions: name, type, description, partition info | metadata |
| 5 | `describe_table` | Live DDL from BigQuery (CREATE TABLE statement) | metadata |
| 6 | `search_tables` | Search tables by keyword, tag, or semantic match on purpose/description | discovery |
| 7 | `get_join_rules` | Join relationships for a table (keys, cardinality, target tables) | discovery |
| 8 | `get_column_values` | Sample values / distinct values / enum values for a column | discovery |
| 9 | `get_example_queries` | Few-shot SQL examples for a table or domain | discovery |
| 10 | `dry_run_query` | Validate SQL syntax + estimate bytes processed / cost | query |
| 11 | `execute_query` | Run SELECT query with full guardrails pipeline | query |
| 12 | `explain_query_error` | Analyze BigQuery error message + suggest fix (for agent retry loops) | query |
| 13 | `get_security_status` | Current rate limit status and enabled security features | query |

### Query Execution Pipeline

```
execute_query(sql)
 │
 ├─ 1. Rate Limit Check (per-client, configurable window)
 ├─ 2. Security Validation (forbidden keywords, injection patterns, max length)
 ├─ 3. YAML Guardrails (table whitelist, partition filter, date range, allowed ops)
 ├─ 4. Query Rewrite (auto LIMIT, table name normalization, max bytes billed)
 ├─ 5. Execute via BigQuery API (with max_bytes_billed cap)
 ├─ 6. PII Masking (hash/redact configured fields)
 ├─ 7. Audit Log
 │
 └─ Return: rows + modifications + masked_fields + executed_query
```

## Implementation Plan

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | 🔲 | Project setup: `pyproject.toml`, FastMCP server skeleton, configs, `.env.example` |
| 2 | 🔲 | Client layer: `BigQueryClient` (base + metadata + discovery + query + ddl mixins) |
| 3 | 🔲 | Service layer: `ConnectionManager` + `BigQueryService` (base + metadata + discovery + query) |
| 4 | 🔲 | Guardrails: security validator, YAML validator, query rewriter, rate limiter, audit logger |
| 5 | 🔲 | PII masker + YAML config parser |
| 6 | 🔲 | Tools layer: metadata tools (list_datasets, list_tables, get_table_info, get_table_schema, describe_table) |
| 7 | 🔲 | Tools layer: discovery tools (search_tables, get_join_rules, get_column_values, get_example_queries) |
| 8 | 🔲 | Tools layer: query tools (dry_run_query, execute_query, explain_query_error, get_security_status) |
| 9 | 🔲 | Unit tests for services and tools |
| 10 | 🔲 | Integration test with real BigQuery + sample config |

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_PROJECT_ID` | Yes | — | Default GCP project ID |
| `GOOGLE_LOCATION` | No | `US` | BigQuery location/region |
| `GOOGLE_KEY_FILE` | No | — | Service account key file path (uses ADC if not set) |
| `DATASETS_FILTER` | No | — | Comma-separated dataset whitelist |
| `READ_ONLY` | No | `true` | Only allow SELECT queries |
| `RATE_LIMIT_MAX_CALLS` | No | `100` | Max calls per time window |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `3600` | Rate limit time window |
| `MAX_BYTES_BILLED` | No | `160GB` | Maximum bytes billed per query |
| `CONFIG_FILE_PATH` | No | `config.yaml` | Path to YAML config file |

### YAML Config (config.yaml)

```yaml
mcp:
  name: "BigQuery MCP Server"
  version: "0.1.0"

bigquery:
  project: "my-gcp-project"
  default_region: "US"
  key_file: "path/to/service-account.json"
  datasets:
    - "analytics"
    - "sales"

guardrails:
  max_rows: 1000
  default_limit: 100
  max_query_length: 10000
  max_bytes_billed: 171798691840  # 160 GiB

pii_masking:
  - name: "email"
    method: "hash"
  - name: "phone_number"
    method: "redact"

tables:
  - name: "analytics.fact_orders"
    purpose: "All completed and pending orders"
    tags: ["orders", "revenue"]
    partition_by: "order_date"
    schema:
      - name: "order_id"
        type: "STRING"
        description: "Unique order identifier"
      - name: "order_date"
        type: "DATE"
        description: "Date the order was placed"
    constraints:
      required_filters: ["order_date"]
      max_days_back: 365
    join_rules:
      - table: "analytics.dim_customers"
        key: "customer_id"
        type: "many_to_one"
    allowed_operations: ["SELECT", "COUNT", "SUM", "AVG"]
    example_queries:
      - question: "How many orders last month?"
        sql: "SELECT COUNT(*) FROM analytics.fact_orders WHERE order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 1 MONTH)"
```

## Quick Start

```bash
# Install in editable mode
pip install -e ".[dev]"

# Set credentials
export GOOGLE_PROJECT_ID="my-project"
export GOOGLE_KEY_FILE="path/to/key.json"

# Run server (stdio transport)
fastmcp run src/bigquery_mcp/server.py:mcp

# Or use FastMCP dev UI
fastmcp dev src/bigquery_mcp/server.py:mcp
```

## MCP Inspector

```bash
npx @modelcontextprotocol/inspector fastmcp run src/bigquery_mcp/server.py:mcp
```

Then open `http://localhost:6274` to browse tools, call them manually, and inspect responses.

## Testing

```bash
pip install -e ".[dev]"

# Run all unit tests
python -m pytest test/units/ -v

# Run specific test file
python -m pytest test/units/services/guardrails/test_security_validator.py -v
```

## Text2SQL Agent Integration

This server is designed to be consumed by a Text2SQL agent. Typical agent workflow:

```
# 1. Discovery — find relevant tables for user question
Agent: search_tables(keyword="revenue by country")     → find candidate tables
Agent: get_table_schema("sales.fact_orders")           → understand columns
Agent: get_join_rules("sales.fact_orders")             → know how to JOIN
Agent: get_column_values("sales.fact_orders", "status") → know valid filter values
Agent: get_example_queries("sales.fact_orders")        → few-shot reference

# 2. Validate generated SQL
Agent: dry_run_query(generated_sql)                    → check syntax + cost

# 3. If dry-run failed, self-correct
Agent: explain_query_error(error_message, sql)         → get fix suggestion
Agent: dry_run_query(repaired_sql)                     → re-validate

# 4. Execute
Agent: execute_query(validated_sql)                    → get results
```

The agent handles NL understanding, SQL generation, and repair loops.
The MCP server handles safe, controlled BigQuery access.

## License

MIT
