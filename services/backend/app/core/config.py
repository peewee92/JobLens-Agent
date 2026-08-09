"""Application configuration loaded from environment / .env.

Single source of truth for runtime settings. Business code must read
DATABASE_URL from here, never hardcode a second copy.
"""
from functools import lru_cache
from typing import Literal

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
    profile_extractor_api_style: Literal["responses", "chat_completions"] = "responses"
    profile_extractor_enable_thinking: bool | None = None
    profile_extractor_max_completion_tokens: int | None = None
    profile_extractor_timeout_seconds: float = 60.0
    requirement_extractor_provider: str = "disabled"
    requirement_extractor_model: str = ""
    requirement_extractor_api_style: Literal["responses", "chat_completions"] = "responses"
    requirement_extractor_enable_thinking: bool | None = None
    requirement_extractor_max_completion_tokens: int | None = None
    requirement_extractor_timeout_seconds: float = 60.0
    semantic_match_provider: str = "disabled"
    semantic_match_model: str = ""
    semantic_match_api_style: Literal["responses", "chat_completions"] = "responses"
    semantic_match_enable_thinking: bool | None = None
    semantic_match_max_completion_tokens: int | None = None
    semantic_match_timeout_seconds: float = 60.0
    requirement_acceptance_private_root: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    web_base_url: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
