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

    read_only: bool = Field(
        True,
        alias="READ_ONLY",
        description="When enabled, only SELECT/WITH/SHOW/DESCRIBE/EXPLAIN queries are allowed.",
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

    max_bytes_billed: int = Field(
        171_798_691_840,  # 160 GiB
        alias="MAX_BYTES_BILLED",
        description="Maximum bytes billed per query. Default: 160 GiB.",
    )

    config_file_path: Optional[str] = Field(
        None,
        alias="CONFIG_FILE_PATH",
        description="Path to YAML config file. Default: config.yaml in project root.",
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


configs = ServerConfigs()
