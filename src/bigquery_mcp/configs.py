from pathlib import Path
from pydantic import Field
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class ServerConfigs(BaseSettings):
    """Minimal env-based configuration — everything else lives in YAML."""

    config_file_path: Optional[str] = Field(
        None,
        alias="CONFIG_FILE_PATH",
        description="Path to YAML config file. Default: config.yaml in project root.",
    )

    log_level: str = Field(
        "INFO",
        alias="LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR).",
    )

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


configs = ServerConfigs()
