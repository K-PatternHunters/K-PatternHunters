"""MongoDB connection and collection accessors for raw_logs, analysis_results, and job_status."""

# Collections:
#   events            — ingested GA4 event records (MONGO_COLLECTION from settings)
#   analysis_results  — final per-job InsightReport outputs
#   job_status        — job lifecycle state: pending | running | done | failed

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from app.core.config import get_settings

_client: AsyncIOMotorClient | None = None


async def connect() -> None:
    """Initialise the Motor client. Call once at application startup."""
    global _client
    settings = get_settings()
    _client = AsyncIOMotorClient(settings.mongodb_uri)


async def disconnect() -> None:
    """Close the Motor client. Call once at application shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def get_collection(name: str) -> AsyncIOMotorCollection:
    """Return a handle to the named collection in the configured database.

    Database resolution order:
    1. MONGODB_URI includes a database name  → use that (get_default_database)
    2. MONGO_DB env var is set to non-default → use that
    3. Fallback to MONGO_DB default value
    """
    if _client is None:
        raise RuntimeError("MongoDB client is not initialised — call connect() first")
    settings = get_settings()
    if settings.MONGODB_URI:
        try:
            return _client.get_default_database()[name]
        except Exception:
            pass
    return _client[settings.MONGO_DB][name]
