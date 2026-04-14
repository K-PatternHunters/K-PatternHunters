"""MongoDB connection and collection accessors for raw_logs, analysis_results, and job_status."""

# Collections:
#   raw_logs          — ingested GA4 event records
#   analysis_results  — final per-job analysis outputs and PPT download URL
#   job_status        — job lifecycle state: pending | running | done | failed

# TODO: initialise AsyncIOMotorClient with MONGODB_URI from config
# TODO: expose get_collection(name) helper used by agents and routers

# from motor.motor_asyncio import AsyncIOMotorClient  # async MongoDB driver

client = None       # Placeholder — replace with AsyncIOMotorClient instance
db = None           # Placeholder — replace with database handle


def get_collection(name: str):
    # Placeholder — implementation pending
    raise NotImplementedError
