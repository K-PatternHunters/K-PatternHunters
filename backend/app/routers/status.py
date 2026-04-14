"""GET /analysis/status/{job_id} — returns current job status and progress for frontend polling."""

# TODO: query job_status collection in MongoDB by job_id
# TODO: return { job_id, status, progress, result_url } — status: pending | running | done | failed

from fastapi import APIRouter

router = APIRouter()


@router.get("/status/{job_id}")
async def get_status(job_id: str):
    # Placeholder — implementation pending
    raise NotImplementedError
