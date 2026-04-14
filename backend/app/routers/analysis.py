"""POST /analysis/run — accepts analysis request, enqueues a Celery task, and returns job_id."""

# TODO: validate request body with AnalysisRequest pydantic model (from app.core.models)
# TODO: enqueue pipeline task via Celery; store initial job_status document in MongoDB
# TODO: return { job_id: str } immediately (non-blocking)

from fastapi import APIRouter

router = APIRouter()


@router.post("/run")
async def run_analysis():
    # Placeholder — implementation pending
    raise NotImplementedError
