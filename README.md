# BigQuery-MCP-Server

BigQuery MCP server with multi-connection support, security guardrails, and YAML-driven configuration. Designed as the **data access layer** for Text2SQL agents and AI data workflows.

## Overview

`bigquery-mcp-server` is a Python MCP server built with [FastMCP](https://github.com/jlowin/fastmcp) that exposes Google BigQuery operations as MCP tools.

**Single YAML config** — connections, guardrails, PII rules, table constraints all in one file. No env var sprawl.

**Multi-connection** — define named connections to multiple BigQuery projects, with automatic routing based on dataset/table.

**Layered guardrails** — global defaults → per-connection overrides → per-table constraints.

## Features

- **Multi-connection**: Named connections to multiple GCP projects with lazy initialization
- **Auto-routing**: Tables automatically route to the correct connection
- **YAML-driven**: Single config file for everything (only `CONFIG_FILE_PATH` env var needed)
- **Layered guardrails**: Global → connection → table level overrides
- **Cross-connection protection**: Block queries spanning multiple connections
- **PII masking**: Hash/redact sensitive columns in query results
- **Rate limiting**: Per-client rate limits
- **Read-only enforcement**: Only SELECT/WITH queries allowed
- **Blocked tables**: Glob-pattern deny list

## Project Structure

```txt
bigquery-mcp-server/
├── pyproject.toml
├── README.md
├── .env.example
├── config.sample.yaml              # ← Single source of truth
├── src/
│   └── bigquery_mcp/
│       ├── __init__.py
│       ├── app.py                      # FastMCP instance
│       ├── server.py                   # Entry point
│       ├── configs.py                  # Minimal env (CONFIG_FILE_PATH, LOG_LEVEL)
│       │
│       ├── clients/bigquery/           # Pure BigQuery API calls
│       │   ├── __init__.py             # BigQueryClient (mixin composition)
│       │   ├── base.py                 # Connection, credentials
│       │   ├── metadata.py             # list_datasets, list_tables, get_table, get_table_schema
│       │   ├── query.py                # execute_query, dry_run, get_distinct_values
│       │   └── ddl.py                  # get_ddl
│       │
│       ├── services/
│       │   ├── connection_manager.py   # Multi-connection manager (lazy-init)
│       │   └── bigquery/               # Service layer (mixin-based)
│       │       ├── __init__.py         # BigQueryService + singleton
│       │       ├── base.py             # Routing, validation, access control
│       │       ├── metadata.py         # MetadataService
│       │       ├── query.py            # QueryService (pipeline integration)
│       │       └── guardrails/         # Security sub-package
│       │           ├── __init__.py     # GuardrailsPipeline orchestrator
│       │           ├── security_validator.py
│       │           ├── query_rewriter.py
│       │           ├── rate_limiter.py
│       │           ├── pii_masker.py
│       │           └── audit_logger.py
│       │
│       ├── tools/bigquery/             # MCP tool definitions (thin layer)
│       │   ├── __init__.py             # Auto-registers all tools
│       │   ├── metadata.py             # list_datasets, list_tables, get_table_schema, describe_table, get_column_values
│       │   └── query.py                # dry_run_query, execute_query, explain_query_error, get_status
│       │
│       └── utils/
│           └── config_parser.py        # YAML parser (connections, routing, guardrails)
│
└── test/
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Tools Layer                                            │
│  9 MCP tools — thin wrappers, format output for LLM    │
├─────────────────────────────────────────────────────────┤
│  Services Layer                                         │
│  Connection routing, guardrails pipeline, PII masking   │
├─────────────────────────────────────────────────────────┤
│  Clients Layer                                          │
│  Pure google-cloud-bigquery API calls                   │
├─────────────────────────────────────────────────────────┤
│  Connection Manager                                     │
│  Dict[name, BigQueryClient] — lazy init per connection  │
└─────────────────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
    BQ Project A         BQ Project B
```

### Connection Routing

```
Agent calls: get_table_schema("analytics.fact_orders")

1. Check tables[] → connection: "prod-us"    (explicit mapping)
2. OR check bq.connections[] → which has "analytics" in datasets?
3. OR fallback to bq.default_connection
→ Use prod-us client
```

### Guardrails Pipeline

Every `execute_query` call passes through the full guardrails pipeline:

```
┌─────────────── PRE-EXECUTE ───────────────┐
│                                           │
│  1. RateLimiter.check()                   │
│     └─ Sliding window (max_calls/window)  │
│                                           │
│  2. SecurityValidator.validate()          │
│     ├─ Query length check                 │
│     ├─ Forbidden keywords (DROP, DELETE…)  │
│     ├─ SQL injection patterns             │
│     └─ Dangerous functions                │
│                                           │
│  3. QueryRewriter.rewrite()               │
│     ├─ Inject LIMIT if missing            │
│     ├─ Cap LIMIT to max_limit             │
│     └─ Skip for pure aggregates           │
│                                           │
├───────────── EXECUTE QUERY ───────────────┤
│                                           │
│  BigQueryClient.execute_query()           │
│                                           │
├─────────────── POST-EXECUTE ──────────────┤
│                                           │
│  4. PIIMasker.mask_rows()                 │
│     ├─ Hash (SHA-256 truncated)           │
│     └─ Redact (***REDACTED***)            │
│                                           │
│  5. AuditLogger.log_query()              │
│     └─ Structured log: query, rows,       │
│        bytes, connection, timestamp        │
│                                           │
│  6. RateLimiter.record()                  │
│                                           │
└───────────────────────────────────────────┘
```

`dry_run_query` only applies **SecurityValidator** (no rewrite/PII/audit since no data is returned).

#### Guardrails modules

| Module | Class | Purpose |
|--------|-------|---------|
| `security_validator.py` | `SecurityValidator` | Static validation — forbidden keywords, injection patterns, dangerous functions, length |
| `query_rewriter.py` | `QueryRewriter` | Auto LIMIT injection, max LIMIT cap, aggregate detection |
| `rate_limiter.py` | `RateLimiter` | Sliding-window rate limiting (configurable calls/window) |
| `pii_masker.py` | `PIIMasker` | Hash or redact PII columns in result rows |
| `audit_logger.py` | `AuditLogger` | Structured audit trail for executed and blocked queries |

## Tools (9)

### Metadata Tools

| # | Tool | Description |
|---|------|-------------|
| 1 | `list_datasets` | List datasets for a connection (or default) |
| 2 | `list_tables` | List tables in a dataset (auto-routes connection) |
| 3 | `get_table_schema` | Column definitions + partition/clustering info |
| 4 | `describe_table` | Live DDL (CREATE TABLE statement) |
| 5 | `get_column_values` | Distinct values for a column (live query) |

### Query Tools

| # | Tool | Description |
|---|------|-------------|
| 6 | `dry_run_query` | Validate SQL + estimate bytes/cost (no execution) |
| 7 | `execute_query` | Run query with full guardrails pipeline |
| 8 | `explain_query_error` | Parse BQ error + suggest fix for retry loops |
| 9 | `get_status` | Connections health, guardrail config, rate limit usage |

### Tool Parameters

All metadata tools accept an optional `connection` parameter. If omitted, auto-routing resolves the connection:

```python
# Explicit connection
list_tables(dataset="analytics", connection="prod-us")

# Auto-route (resolves from YAML config)
get_table_schema(table_name="analytics.fact_orders")

# Dry run before executing
dry_run_query(query="SELECT * FROM analytics.fact_orders WHERE order_date > '2024-01-01'")

# Execute with guardrails
execute_query(query="SELECT customer_id, email, total FROM analytics.fact_orders LIMIT 10")
# → email column auto-masked by PII rules
```

### Output Format

All tools return **LLM-friendly strings** (not raw dicts). Examples:

```
# list_datasets output
Datasets on 'prod-us' (3):
  - analytics  (location: US)
  - sales  (location: US)
  - marketing  (location: US)

# dry_run_query output
Query is valid.
  Connection: prod-us
  Estimated bytes: 1.23 GiB (1,321,205,760 bytes)
  Referenced tables: analytics.fact_orders
  Output columns: customer_id (INTEGER), email (STRING), total (FLOAT)

# get_status output
Server Status:
  Default connection: prod-us
Connections:
  - prod-us: connected (project: your-prod-project)
  - staging-eu: not initialized (project: your-staging-project)
Guardrails:
  Read-only: True
  Default LIMIT: 100
  Max LIMIT: 1000
  Rate limit: 3/100 (window: 3600s)
```

## Configuration

### YAML Config (single source of truth)

```yaml
mcp:
  name: bigquery-mcp
  version: 0.3.0

bq:
  default_connection: prod-us
  connections:
    prod-us:
      project: your-prod-project
      default_region: US
      key_file: /secrets/prod-us-sa.json
      datasets:
        - analytics
        - sales

    staging-eu:
      project: your-staging-project
      default_region: europe-west4
      key_file: /secrets/staging-eu-sa.json
      datasets:
        - staging_analytics
      max_bytes_billed: 5368709120    # per-connection override

guardrails:
  read_only: true
  default_limit: 100
  max_limit: 1000
  max_bytes_billed: 10737418240      # 10 GiB global
  max_query_length: 10000
  forbid_cross_connection: true
  rate_limit:
    max_calls: 100
    window_seconds: 3600

pii:
  - column: email
    method: hash
  - column: phone_number
    method: redact

tables:
  - name: analytics.fact_orders
    connection: prod-us
    constraints:
      required_filters: [order_date]
      max_days_back: 365
    allowed_operations: [SELECT, COUNT, SUM, AVG, GROUP BY, ORDER BY]

blocked_tables:
  - "internal.*"
  - "temp.*"
```

### Environment Variables

Only 2 env vars needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONFIG_FILE_PATH` | `config.yaml` | Path to YAML config |
| `LOG_LEVEL` | `INFO` | Logging level |

### Guardrails Layering

```
Global (guardrails section)
  └─ Per-connection (bq.connections.X.max_bytes_billed)
      └─ Per-table (tables[].constraints)
```

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Create config
cp config.sample.yaml config.yaml
# Edit config.yaml with your project/credentials

# Run
fastmcp run src/bigquery_mcp/server.py:mcp
```

## Implementation Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ | Project scaffold + configs |
| 2 | ✅ | Client layer (metadata + query + ddl) |
| 3 | ✅ | Service layer (connection manager + metadata + query) |
| 4 | ✅ | Multi-connection + YAML-driven config |
| 5 | ✅ | Guardrails pipeline (security, rewriter, rate limiter, PII masker, audit) |
| 6 | ✅ | Tools layer (9 MCP tools) |
| 7 | 🔲 | Unit tests |

## License

MIT
