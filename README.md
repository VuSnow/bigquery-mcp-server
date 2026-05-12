# bigquery-mcp-server

BigQuery MCP server providing schema introspection, dry-run validation, and query execution tools with security guardrails. Designed as the **data access layer** for Text2SQL agents and AI data workflows.

## Overview

`bigquery-mcp-server` is a Python MCP server built with [FastMCP](https://github.com/jlowin/fastmcp) that exposes Google BigQuery operations as well-defined MCP tools.

This server is a **database driver with guardrails** — it handles safe BigQuery access (schema, validation, execution, PII masking) but does **not** store domain knowledge (table descriptions, join rules, examples). Domain knowledge belongs in the Text2SQL agent layer.

```
Text2SQL Agent (owns knowledge)
├── Vector store: table descriptions, examples, glossary
├── Semantic layer: join rules, metrics, dimensions
├── Retrieval: embedding search
└── Calls MCP for data access only
         │
         ▼
BQ MCP Server (owns access + guardrails)
├── Schema introspection (live from BigQuery API)
├── Guardrails (security, PII, rate limit, blocked tables)
├── Dry-run validation
├── Query execution
└── No domain knowledge, no descriptions, no examples
         │
         ▼
    Google BigQuery
```

## Features

- Connect to BigQuery via service account or application default credentials
- Expose BigQuery operations as FastMCP tools
- List datasets and tables
- Inspect table schema and DDL
- Get distinct column values (for filter value awareness)
- Dry-run query validation (syntax + cost estimation)
- Execute read-only queries with full guardrails
- 3 access modes: `yaml_only` | `auto_discovery` | `hybrid`
- Config-driven guardrails (toggleable via env vars)
- YAML config for table constraints, blocked tables, PII masking
- Rate limiting and audit logging
- Read-only mode by default

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
│       │       ├── metadata.py             # list_datasets, list_tables, get_table, get_table_schema
│       │       ├── query.py                # execute_query, dry_run, get_distinct_values
│       │       └── ddl.py                  # get_ddl (DDL retrieval)
│       │
│       ├── services/
│       │   ├── __init__.py
│       │   ├── connection_manager.py       # Connection state machine (singleton)
│       │   └── bigquery/                   # BigQuery service layer (mixin-based)
│       │       ├── __init__.py             # BigQueryService (composed) + singleton
│       │       ├── base.py                 # BaseService (ensure_connected, access checks, validation)
│       │       ├── metadata.py             # MetadataService (list, schema, DDL, column values)
│       │       ├── query.py                # QueryService (execute, dry_run, explain_error)
│       │       └── guardrails/             # Security & guardrails sub-package
│       │           ├── __init__.py
│       │           ├── security_validator.py   # Forbidden keywords, injection patterns, query length
│       │           ├── yaml_validator.py       # Blocked tables, constraints, mode-aware whitelist
│       │           ├── query_rewriter.py       # Auto LIMIT, enforce max limit
│       │           ├── pii_masker.py           # Hash/redact PII fields in results
│       │           ├── rate_limiter.py         # Per-client rate limiting
│       │           └── audit_logger.py         # Security audit logging
│       │
│       ├── tools/                          # Tool definitions (thin layer, delegates to services)
│       │   ├── __init__.py
│       │   └── bigquery/                   # BigQuery tools package
│       │       ├── __init__.py             # Re-exports all tools
│       │       ├── metadata.py             # list_datasets, list_tables, get_table_schema, describe_table, get_column_values
│       │       └── query.py                # execute_query, dry_run_query, explain_query_error, get_security_status
│       │
│       └── utils/
│           ├── __init__.py
│           ├── config_parser.py            # YAML config loader (guardrails, PII, blocked tables)
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
│  - Access control (blocked tables, mode-aware whitelist)│
│  - Guardrails pipeline (validate → rewrite → execute)  │
│  - Rate limiting & audit logging                        │
│  - PII masking on results                              │
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

- **Data access only, no domain knowledge**: Descriptions, join rules, examples belong in the Text2SQL agent, not here.
- **3 access modes**: `yaml_only` (strict whitelist), `auto_discovery` (introspect all), `hybrid` (introspect + guardrails overlay).
- **Config-driven guardrails**: Each pipeline step toggleable via env vars. YAML defines domain rules (constraints, blocked tables, PII).
- **Mixin composition**: Client and service layers use base + mixins → composed class.
- **Singleton services**: `connection_manager` and `bigquery_service` are module-level singletons shared across all tools.

## Tools (9)

| # | Tool | Description | Layer |
|---|------|-------------|-------|
| 1 | `list_datasets` | List available BigQuery datasets | metadata |
| 2 | `list_tables` | List tables in a dataset (filtered by access mode + blocked list) | metadata |
| 3 | `get_table_schema` | Column definitions + partition info + basic table metadata | metadata |
| 4 | `describe_table` | Live DDL from BigQuery (CREATE TABLE statement) | metadata |
| 5 | `get_column_values` | Distinct values for a column (live query) | metadata |
| 6 | `dry_run_query` | Validate SQL syntax + estimate bytes processed / cost | query |
| 7 | `execute_query` | Run SELECT query with full guardrails pipeline | query |
| 8 | `explain_query_error` | Analyze BigQuery error message + suggest fix | query |
| 9 | `get_security_status` | Current guardrail toggles, rate limit, access mode | query |

### Query Execution Pipeline

```
execute_query(sql)
 │
 ├─ 1. Rate Limit Check         (if ENABLE_RATE_LIMITER=true)
 ├─ 2. Security Validation      (if ENABLE_SECURITY_VALIDATOR=true && ALLOW_WRITE_TOOLS=false)
 ├─ 3. YAML Guardrails          (if ENABLE_YAML_VALIDATOR=true — mode-aware)
 ├─ 4. Query Rewrite            (if ENABLE_QUERY_REWRITER=true)
 ├─ 5. Execute via BigQuery API  (with max_bytes_billed cap)
 ├─ 6. PII Masking              (if ENABLE_PII_MASKING=true)
 ├─ 7. Audit Log                (if ENABLE_AUDIT_LOGGING=true)
 │
 └─ Return: rows + modifications + masked_fields + executed_query
```

## Implementation Plan

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Project setup: `pyproject.toml`, FastMCP server skeleton, configs, `.env.example` |
| 2 | ✅ Done | Client layer: `BigQueryClient` (base + metadata + query + ddl mixins) |
| 3 | ✅ Done | Service layer: `ConnectionManager` + `BigQueryService` (base + metadata + query) |
| 4 | 🔲 | Guardrails: security validator, YAML validator, query rewriter, rate limiter, audit logger |
| 5 | 🔲 | PII masker + YAML config parser (blocked tables, constraints) |
| 6 | 🔲 | Tools layer: metadata tools (list_datasets, list_tables, get_table_schema, describe_table, get_column_values) |
| 7 | 🔲 | Tools layer: query tools (dry_run_query, execute_query, explain_query_error, get_security_status) |
| 8 | 🔲 | Unit tests for services and tools |
| 9 | 🔲 | Integration test with real BigQuery + sample config |

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GOOGLE_PROJECT_ID` | Yes | — | Default GCP project ID |
| `GOOGLE_LOCATION` | No | `US` | BigQuery location/region |
| `GOOGLE_KEY_FILE` | No | — | Service account key file path (uses ADC if not set) |
| `DATASETS_FILTER` | No | — | Comma-separated dataset whitelist |
| `TABLE_ACCESS_MODE` | No | `hybrid` | `yaml_only` / `auto_discovery` / `hybrid` |
| `ALLOW_WRITE_TOOLS` | No | `false` | Skip security validator when true |
| `ENABLE_SECURITY_VALIDATOR` | No | `true` | Toggle forbidden keyword checks |
| `ENABLE_YAML_VALIDATOR` | No | `true` | Toggle YAML-based guardrails |
| `ENABLE_QUERY_REWRITER` | No | `true` | Toggle auto LIMIT and rewriting |
| `ENABLE_RATE_LIMITER` | No | `true` | Toggle rate limiting |
| `ENABLE_PII_MASKING` | No | `true` | Toggle PII field masking |
| `ENABLE_AUDIT_LOGGING` | No | `true` | Toggle audit logging |
| `MAX_QUERY_LENGTH` | No | `10000` | Max query length in chars |
| `MAX_ROWS` | No | `1000` | Max rows returned (caps LIMIT) |
| `DEFAULT_LIMIT` | No | `100` | Default LIMIT added when missing |
| `MAX_BYTES_BILLED` | No | `10 GiB` | Max bytes billed per query |
| `RATE_LIMIT_MAX_CALLS` | No | `100` | Max calls per window |
| `RATE_LIMIT_WINDOW_SECONDS` | No | `3600` | Rate limit window |
| `CONFIG_FILE_PATH` | No | `config.yaml` | Path to YAML config file |

### YAML Config (guardrails only — no domain knowledge)

```yaml
settings:
  table_access_mode: "hybrid"

guardrails:
  max_rows: 1000
  default_limit: 100
  max_bytes_billed: 10737418240  # 10 GiB

pii_masking:
  - name: "email"
    method: "hash"
  - name: "phone_number"
    method: "redact"
  - name: "full_name"
    method: "redact"

# Per-table constraints (guardrails only, no descriptions/examples)
tables:
  - name: "analytics.fact_orders"
    constraints:
      required_filters: ["order_date"]
      max_days_back: 365
      disallowed_patterns: ["SELECT *"]
    allowed_operations: ["SELECT", "COUNT", "SUM", "AVG", "GROUP BY", "ORDER BY"]

  - name: "analytics.dim_customers"
    constraints:
      disallowed_patterns: ["SELECT *", "LIKE '%@%'"]
    allowed_operations: ["SELECT", "COUNT", "GROUP BY", "ORDER BY"]

# Explicit deny list (overrides everything)
blocked_tables:
  - "internal.pii_raw_data"
  - "internal.audit_logs"
  - "temp.*"
```

### Access Modes

| Mode | `list_tables` | Whitelist | Blocked | Constraints |
|------|---------------|-----------|---------|-------------|
| `yaml_only` | Only YAML tables | ✅ enforced | ✅ | ✅ |
| `auto_discovery` | All from BQ API | ❌ | ✅ | ❌ |
| `hybrid` | All from BQ API | ❌ | ✅ | ✅ for YAML tables |

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
python -m pytest test/units/ -v
```

## Text2SQL Agent Integration

This server is the data access layer. The agent owns domain knowledge separately.

```
# 1. Schema introspection
Agent: list_tables("analytics")                        → discover tables
Agent: get_table_schema("analytics.fact_orders")       → get columns
Agent: get_column_values("analytics.fact_orders", "status") → valid filter values

# 2. Validate generated SQL
Agent: dry_run_query(generated_sql)                    → syntax + cost check

# 3. Self-correct on failure
Agent: explain_query_error(error, sql)                 → fix suggestions
Agent: dry_run_query(repaired_sql)                     → re-validate

# 4. Execute
Agent: execute_query(validated_sql)                    → results
```

Domain knowledge (table descriptions, join rules, examples) lives in the agent's own vector store — not in this MCP server.

## License

MIT
