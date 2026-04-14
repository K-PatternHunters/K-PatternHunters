"""Loads and validates environment variables using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MONGODB_URI: str = "mongodb://localhost:27017"
    QDRANT_URL: str = "http://localhost:6333"
    REDIS_URL: str = "redis://localhost:6379"
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
