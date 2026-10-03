"""Global configuration management using pydantic-settings and YAML."""

import socket
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """InfraOps global settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_prefix="INFRAOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: str = Field(default="dev-secret-key", alias="INFRAOPS_API_KEY")
    server_url: str = Field(default="http://localhost:8000", alias="INFRAOPS_SERVER_URL")
    db_url: str = Field(default="sqlite:///./data/infraops.db", alias="INFRAOPS_DB_URL")
    sandbox_dir: str = Field(default="./sandbox", alias="INFRAOPS_SANDBOX_DIR")
    aws_mode: str = Field(default="mock", alias="INFRAOPS_AWS_MODE")
    aws_region: str = Field(default="ap-south-1", alias="INFRAOPS_AWS_REGION")
    auto_remediate: bool = Field(default=True, alias="INFRAOPS_AUTO_REMEDIATE")
    host_id: Optional[str] = Field(default=None, alias="INFRAOPS_HOST_ID")
    test_thresholds: bool = Field(default=False, alias="INFRAOPS_TEST_THRESHOLDS")

    def get_effective_host_id(self) -> str:
        """Return configured host_id or fall back to system hostname."""
        if self.host_id and self.host_id.strip():
            return self.host_id.strip()
        return socket.gethostname()

    def get_sandbox_path(self) -> Path:
        """Return resolved Path to the sandbox directory."""
        return Path(self.sandbox_dir).resolve()


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton accessor for settings."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> Settings:
    """Reset settings instance (useful in tests when env vars change)."""
    global _settings
    _settings = Settings()
    return _settings


def load_yaml(file_path: str | Path) -> Dict[str, Any]:
    """Safely load and parse a YAML file."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}
