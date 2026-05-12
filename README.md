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
- **Read-only enforcement**: Only SELECT/WITH/SHOW/DESCRIBE/EXPLAIN queries allowed
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
│  1. RateLimiter.check_and_reserve()       │
│     └─ Sliding window (atomic check+slot) │
│                                           │
│  2. SecurityValidator.validate()          │
│     ├─ Query length check                 │
│     ├─ Read-only starts-with check        │
│     ├─ Strip comments & string literals   │
│     ├─ Forbidden keywords (DROP, DELETE…)  │
│     ├─ SQL injection patterns             │
│     └─ Dangerous functions                │
│                                           │
│  3. QueryRewriter.rewrite()               │
│     ├─ Inject LIMIT if missing            │
│     ├─ Cap LIMIT to max_limit (outer only)│
│     └─ Skip for pure aggregates (w/ alias)│
│                                           │
├───────────── EXECUTE QUERY ───────────────┤
│                                           │
│  BigQueryClient.execute_query()           │
│     └─ timeout on .result() (not .query())│
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
└───────────────────────────────────────────┘
```

`dry_run_query` only applies **SecurityValidator** (no rewrite/PII/audit since no data is returned).

#### Guardrails modules

| Module | Class | Purpose |
|--------|-------|---------|
| `security_validator.py` | `SecurityValidator` | Static validation — forbidden keywords, injection patterns, dangerous functions, length. Strips SQL comments and handles escaped/doubled quotes to avoid false positives. |
| `query_rewriter.py` | `QueryRewriter` | Auto LIMIT injection, max LIMIT cap (targets outer query, not subqueries), aggregate detection, CTE-aware, handles trailing comments |
| `rate_limiter.py` | `RateLimiter` | Thread-safe sliding-window rate limiting (configurable calls/window) |
| `pii_masker.py` | `PIIMasker` | Case-insensitive hash or redact PII columns in result rows |
| `audit_logger.py` | `AuditLogger` | Structured audit trail for executed and blocked queries |

## Tools (9)

| Tool | Description | Params |
|------|-------------|--------|
| `list_datasets` | List all accessible BigQuery datasets with location | <ul><li>`connection` — Connection name. Default: default connection</li></ul> |
| `list_tables` | List all tables in a dataset with row counts | <ul><li>`dataset` — Dataset ID (e.g., `"analytics"`)</li><li>`connection` — Connection name (optional, auto-routes)</li></ul> |
| `get_table_schema` | Get column definitions + partition/clustering info | <ul><li>`table_name` — Fully qualified name (`dataset.table` or `project.dataset.table`)</li><li>`connection` — Connection name (optional, auto-routes)</li></ul> |
| `describe_table` | Get live DDL (CREATE TABLE statement) | <ul><li>`table_name` — Fully qualified table name</li><li>`connection` — Connection name (optional, auto-routes)</li></ul> |
| `get_column_values` | Get distinct values for a column (live query) | <ul><li>`table_name` — Fully qualified table name</li><li>`column` — Column name</li><li>`limit` — Max distinct values. Default: `50`</li><li>`connection` — Connection name (optional, auto-routes)</li></ul> |
| `dry_run_query` | Validate SQL + estimate bytes/cost (no execution) | <ul><li>`query` — SQL query (SELECT/WITH only)</li><li>`connection` — Connection name (optional)</li></ul> |
| `execute_query` | Run query with full guardrails pipeline | <ul><li>`query` — SQL query (SELECT/WITH only)</li><li>`connection` — Connection name (optional, auto-routes)</li></ul> |
| `explain_query_error` | Analyze BQ error + suggest fixes for retry loops | <ul><li>`error_message` — The error message from a failed query</li><li>`query` — The SQL query that produced the error</li></ul> |
| `get_status` | Get connections health, guardrail config, rate limit | *(none)* |

> **Auto-routing**: When `connection` is omitted, the server resolves the correct connection from YAML config based on dataset/table name. Zero config needed per-call.
>
> **Read-only**: All query tools enforce read-only mode. Only `SELECT`, `WITH`, `SHOW`, `DESCRIBE`, `EXPLAIN` are allowed.

### Usage Examples

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
  - prod-us: connected
  - staging-eu: disconnected
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
  query_timeout_seconds: 300         # max execution time per query
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
# Install in editable mode
pip install -e ".[dev]"

# Create config
cp config.sample.yaml config.yaml
# Edit config.yaml with your project/credentials

# Run server (stdio transport)
fastmcp run src/bigquery_mcp/server.py:mcp

# Or use FastMCP dev UI
fastmcp dev src/bigquery_mcp/server.py:mcp
```

## MCP Inspector

[MCP Inspector](https://github.com/modelcontextprotocol/inspector) is a browser-based tool for interactively testing MCP servers and their tools.

```bash
# Run MCP Inspector against this server (npx, no install required)
npx @modelcontextprotocol/inspector fastmcp run src/bigquery_mcp/server.py:mcp
```

Then open `http://localhost:6274` in your browser. From there you can:
- Browse all 9 registered tools and their input schemas
- Call tools manually and inspect structured responses
- Debug tool outputs without needing a full MCP client

> **Note**: Ensure `config.yaml` exists with valid BigQuery credentials before running.

### Install Node.js (required for npx)

**macOS**
```bash
brew install node
```

**Ubuntu / Debian**
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

**Windows**

Download and run the installer from [nodejs.org](https://nodejs.org).

Verify installation:
```bash
node --version   # should be ≥ 18
npx --version
```

## Testing

```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all unit tests
python -m pytest test/ -v

# Run specific test file
python -m pytest test/test_security_validator.py -v

# Run with short traceback
python -m pytest test/ --tb=short

# Run with coverage (if pytest-cov installed)
python -m pytest test/ --cov=bigquery_mcp --cov-report=term-missing
```

> **Note**: Tests mock all BigQuery interactions — no running BigQuery instance or GCP credentials required for unit tests.

**196 tests — all passing.**

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_security_validator.py` | 47 | Forbidden keywords, injection patterns, dangerous functions, SQL comments, escaped quotes, exotic bypass attempts (CRLF, null byte, unicode, backtick identifiers) |
| `test_query_rewriter.py` | 36 | LIMIT injection/capping, aggregate detection (with aliases), CTE handling, trailing comments, subquery preservation, UNION, OFFSET, string-literal LIMIT, huge numbers |
| `test_services.py` | 32 | MetadataService + QueryService, timeout semantics, table/column name injection validation |
| `test_config_parser.py` | 20 | Connections, routing, guardrails layering, PII, blocked tables |
| `test_pii_masker.py` | 15 | Hash, redact, multiple rules, null/empty edge cases, case-insensitive matching |
| `test_tools.py` | 13 | Output formatting for all 9 MCP tools |
| `test_guardrails_pipeline.py` | 11 | End-to-end pre/post-execute orchestration |
| `test_rate_limiter.py` | 9 | Sliding window, expiration, status reporting, thread-safety under concurrent load |
| `test_connection_manager.py` | 7 | Lazy init, reuse, disconnect, error handling |
| `test_audit_logger.py` | 6 | Query logging, blocked logging, error truncation |

## Implementation Status

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ | Project scaffold + configs |
| 2 | ✅ | Client layer (metadata + query + ddl) |
| 3 | ✅ | Service layer (connection manager + metadata + query) |
| 4 | ✅ | Multi-connection + YAML-driven config |
| 5 | ✅ | Guardrails pipeline (security, rewriter, rate limiter, PII masker, audit) |
| 6 | ✅ | Tools layer (9 MCP tools) |
| 7 | ✅ | Unit tests (196 tests) |
| 8 | ✅ | Production hardening (comment-aware validation, CTE-safe rewriting, case-insensitive PII, parallel metadata fetching) |
| 9 | ✅ | Deep investigation & fixes (timeout semantics, aliased aggregate detection, exotic bypass testing, input validation coverage) |

## License

MIT
