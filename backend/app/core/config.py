"""Loads and validates environment variables using pydantic-settings."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# 루트 .env 경로 (backend/app/core/config.py → 4단계 위)
_ROOT_ENV = Path(__file__).parents[3] / ".env"


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    TAVILY_API_KEY: str = ""

    # MongoDB — individual components (used to build URI when MONGODB_URI is not set)
    MONGO_USER: str = ""
    MONGO_PASSWORD: str = ""
    MONGO_HOST: str = "localhost"
    MONGO_PORT: int = 27017
    MONGO_DB: str = "ga4_ecommerce"
    MONGO_COLLECTION: str = "events"
    # Full URI override — takes precedence over individual components when non-empty
    MONGODB_URI: str = ""

    QDRANT_URL: str = "http://localhost:6333"
    REDIS_URL: str = "redis://localhost:6379/0"
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret"

    model_config = {"env_file": str(_ROOT_ENV), "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def mongodb_uri(self) -> str:
        """Return the full MongoDB connection URI."""
        if self.MONGODB_URI:
            return self.MONGODB_URI
        if self.MONGO_USER and self.MONGO_PASSWORD:
            return (
                f"mongodb://{self.MONGO_USER}:{self.MONGO_PASSWORD}"
                f"@{self.MONGO_HOST}:{self.MONGO_PORT}/?authSource=admin"
            )
        return f"mongodb://{self.MONGO_HOST}:{self.MONGO_PORT}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
