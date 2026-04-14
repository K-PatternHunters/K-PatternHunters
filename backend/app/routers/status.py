"""GET /analysis/status/{job_id}    — job lifecycle polling
GET /analysis/result/{job_id}    — full InsightReport once job is done
GET /analysis/download/{job_id}  — download generated .pptx file"""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.models import JobStatus
from app.db.mongo import get_collection

router = APIRouter()


@router.get("/status/{job_id}", response_model=JobStatus)
async def get_status(job_id: str):
    """Return current job status and progress for frontend polling."""
    doc = await get_collection("job_status").find_one({"job_id": job_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatus(
        job_id=doc["job_id"],
        status=doc["status"],
        progress=doc.get("progress", 0),
        result_url=doc.get("result_url"),
        error=doc.get("error"),
    )


@router.get("/result/{job_id}")
async def get_result(job_id: str):
    """Return the full InsightReport for a completed job."""
    status_doc = await get_collection("job_status").find_one({"job_id": job_id})
    if status_doc is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if status_doc.get("status") != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not done yet (status={status_doc.get('status')})",
        )

    result_doc = await get_collection("analysis_results").find_one({"job_id": job_id})
    if result_doc is None:
        raise HTTPException(status_code=404, detail="Result not found")

    result_doc.pop("_id", None)
    # Convert datetime to ISO string for JSON serialisation
    if hasattr(result_doc.get("created_at"), "isoformat"):
        result_doc["created_at"] = result_doc["created_at"].isoformat()

    return result_doc


@router.get("/download/{job_id}")
async def download_ppt(job_id: str):
    """Download the generated .pptx file for a completed job."""
    status_doc = await get_collection("job_status").find_one({"job_id": job_id})
    if status_doc is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if status_doc.get("status") != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Job is not done yet (status={status_doc.get('status')})",
        )

    ppt_url = status_doc.get("ppt_url")
    if not ppt_url:
        raise HTTPException(status_code=404, detail="PPT file not found for this job")
    if not os.path.isfile(ppt_url):
        raise HTTPException(status_code=404, detail=f"PPT file missing on server: {ppt_url}")

    filename = os.path.basename(ppt_url)
    return FileResponse(
        path=ppt_url,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )
