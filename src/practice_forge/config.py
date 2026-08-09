"""Central runtime settings, loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")

    database_url: str = Field(
        default="postgresql+psycopg://practice_forge:practice_forge@localhost:5432/practice_forge",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    docker_host: str = Field(default="", alias="DOCKER_HOST")

    sandbox_mem_limit_mb: int = Field(default=2048, alias="SANDBOX_MEM_LIMIT_MB")
    sandbox_cpu_seconds_part_a: int = Field(default=15, alias="SANDBOX_CPU_SECONDS_PART_A")
    sandbox_cpu_seconds_part_b: int = Field(default=15, alias="SANDBOX_CPU_SECONDS_PART_B")

    environment: str = Field(default="development", alias="ENVIRONMENT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    profiles_dir: Path = REPO_ROOT / "profiles"
    prompts_dir: Path = REPO_ROOT / "prompts"


@lru_cache
def get_settings() -> Settings:
    return Settings()
