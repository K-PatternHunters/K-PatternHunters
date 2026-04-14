"""POST /analysis/run — accepts analysis request, runs the LangGraph pipeline
in a FastAPI background task, and returns job_id.

Each analysis agent queries MongoDB directly via aggregation pipelines —
raw_logs are never loaded into Python memory.
"""

import traceback
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.models import AnalysisRequest
from app.db.mongo import get_collection
from app.graph.pipeline import analysis_graph

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Background pipeline task
# ──────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, request: AnalysisRequest) -> None:
    job_col = get_collection("job_status")

    try:
        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"status": "running", "progress": 10}},
        )

        # ── Run LangGraph pipeline ─────────────────────────────────────────────
        # Each agent fetches its own data from MongoDB via aggregation.
        initial_state: dict = {
            "job_id": job_id,
            "period": request.period,
            "domain_description": request.domain_description,
            "week_start": request.week_start,
            "week_end": request.week_end,
        }

        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"progress": 20}},
        )

        result_state: dict = await analysis_graph.ainvoke(initial_state)

        # ── Persist result ─────────────────────────────────────────────────────
        insight_report = result_state.get("insight_report", {})
        ppt_url = result_state.get("ppt_url")
        result_col = get_collection("analysis_results")
        await result_col.replace_one(
            {"job_id": job_id},
            {
                "job_id": job_id,
                "insight_report": insight_report,
                "ppt_url": ppt_url,
                "created_at": datetime.now(tz=timezone.utc),
            },
            upsert=True,
        )

        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"status": "done", "progress": 100, "ppt_url": ppt_url}},
        )

    except Exception as exc:
        await job_col.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "status": "failed",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            },
        )
        raise


# ──────────────────────────────────────────────────────────────────────────────
# Endpoint
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/run", status_code=202)
async def run_analysis(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Enqueue a pipeline run and return a job_id for status polling.

    The pipeline runs asynchronously — poll GET /analysis/status/{job_id}
    until status == "done", then fetch the result from GET /analysis/result/{job_id}.
    """
    if not request.domain_description:
        raise HTTPException(status_code=422, detail="domain_description is required")

    job_id = str(uuid.uuid4())

    job_col = get_collection("job_status")
    await job_col.insert_one(
        {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "created_at": datetime.now(tz=timezone.utc),
            "request": request.model_dump(),
        }
    )

    background_tasks.add_task(_run_pipeline, job_id, request)
    return {"job_id": job_id}
