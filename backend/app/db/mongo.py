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
    """Return a handle to the named collection in the configured database."""
    if _client is None:
        raise RuntimeError("MongoDB client is not initialised — call connect() first")
    return _client[get_settings().MONGO_DB][name]
