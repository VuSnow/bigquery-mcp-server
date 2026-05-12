from pathlib import Path
from pydantic import Field
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class ServerConfigs(BaseSettings):
    """Configuration for the BigQuery MCP Server."""

    project_id: str = Field(
        ...,
        alias="GOOGLE_PROJECT_ID",
        description="Default GCP project ID for BigQuery operations.",
    )

    location: str = Field(
        "us-west1",
        alias="GOOGLE_LOCATION",
        description="BigQuery location/region.",
    )

    key_file: Optional[str] = Field(
        None,
        alias="GOOGLE_KEY_FILE",
        description="Path to service account key file. Uses ADC if not set.",
    )

    datasets_filter: Optional[str] = Field(
        None,
        alias="DATASETS_FILTER",
        description="Comma-separated list of datasets to expose. Empty = all datasets.",
    )

    config_file_path: Optional[str] = Field(
        None,
        alias="CONFIG_FILE_PATH",
        description="Path to YAML config file. Default: config.yaml in project root.",
    )

    table_access_mode: str = Field(
        "hybrid",
        alias="TABLE_ACCESS_MODE",
        description="Table access mode: yaml_only | auto_discovery | hybrid.",
    )

    read_only: bool = Field(
        True,
        alias="READ_ONLY",
        description="When enabled, only SELECT/WITH/SHOW/DESCRIBE/EXPLAIN queries are allowed.",
    )

    allow_write_tools: bool = Field(
        False,
        alias="ALLOW_WRITE_TOOLS",
        description="When true, skip security validator (allow INSERT/UPDATE/DELETE).",
    )

    enable_security_validator: bool = Field(
        True,
        alias="ENABLE_SECURITY_VALIDATOR",
        description="Enable forbidden keyword and injection pattern checks.",
    )

    enable_yaml_validator: bool = Field(
        True,
        alias="ENABLE_YAML_VALIDATOR",
        description="Enable YAML-based table whitelist and constraint checks.",
    )

    enable_query_rewriter: bool = Field(
        True,
        alias="ENABLE_QUERY_REWRITER",
        description="Enable auto LIMIT and query rewriting.",
    )

    enable_rate_limiter: bool = Field(
        True,
        alias="ENABLE_RATE_LIMITER",
        description="Enable per-client rate limiting.",
    )

    enable_pii_masking: bool = Field(
        True,
        alias="ENABLE_PII_MASKING",
        description="Enable PII field masking in query results.",
    )

    enable_audit_logging: bool = Field(
        True,
        alias="ENABLE_AUDIT_LOGGING",
        description="Enable security audit logging.",
    )

    max_query_length: int = Field(
        10_000,
        alias="MAX_QUERY_LENGTH",
        description="Maximum allowed query length in characters.",
    )

    max_rows: int = Field(
        1000,
        alias="MAX_ROWS",
        description="Maximum rows returned per query (caps LIMIT).",
    )

    default_limit: int = Field(
        100,
        alias="DEFAULT_LIMIT",
        description="Default LIMIT added when query has no LIMIT clause.",
    )

    max_bytes_billed: int = Field(
        10_737_418_240,  # 10 GiB
        alias="MAX_BYTES_BILLED",
        description="Maximum bytes billed per query. Default: 10 GiB.",
    )

    rate_limit_max_calls: int = Field(
        100,
        alias="RATE_LIMIT_MAX_CALLS",
        description="Maximum number of calls per time window.",
    )

    rate_limit_window_seconds: int = Field(
        3600,
        alias="RATE_LIMIT_WINDOW_SECONDS",
        description="Rate limit time window in seconds.",
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


configs = ServerConfigs()
