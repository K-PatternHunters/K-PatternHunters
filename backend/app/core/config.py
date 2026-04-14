"""Loads and validates all environment variables using Pydantic BaseSettings."""

# TODO: define Settings(BaseSettings) with:
#   OPENAI_API_KEY, MONGODB_URI, QDRANT_URL, REDIS_URL, APP_ENV, SECRET_KEY
# TODO: expose a cached `get_settings()` dependency for FastAPI

# from pydantic_settings import BaseSettings  # pydantic v2 / langchain v1.0+ compatible


class Settings:
    # Placeholder — replace with BaseSettings subclass
    OPENAI_API_KEY: str = ""
    MONGODB_URI: str = ""
    QDRANT_URL: str = ""
    REDIS_URL: str = ""
    APP_ENV: str = "development"
    SECRET_KEY: str = ""


def get_settings() -> Settings:
    # Placeholder — implementation pending
    return Settings()
