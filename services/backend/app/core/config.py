"""Application configuration loaded from environment / .env.

Single source of truth for runtime settings. Business code must read
DATABASE_URL from here, never hardcode a second copy.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "local"
    database_url: str = "sqlite:///./data/joblens.db"
    profile_extractor_provider: str = "disabled"
    profile_extractor_model: str = ""
    profile_extractor_timeout_seconds: float = 60.0
    requirement_extractor_provider: str = "disabled"
    requirement_extractor_model: str = ""
    requirement_extractor_timeout_seconds: float = 60.0
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
