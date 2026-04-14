"""POST /analysis/run — accepts analysis request, loads raw_logs from MongoDB,
runs the LangGraph pipeline in a FastAPI background task, and returns job_id."""

import traceback
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.config import get_settings
from app.core.models import AnalysisRequest
from app.db.mongo import get_collection
from app.graph.pipeline import analysis_graph

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_param_value(v) -> dict:
    if isinstance(v, int):
        return {"int_value": v}
    if isinstance(v, float):
        return {"float_value": v}
    return {"string_value": str(v)}


def _prepare_doc(doc: dict) -> dict:
    """Convert a MongoDB event document into a GA4-compatible format for the pipeline.

    transform.py removed the original `event_params` array and stored it as
    `event_params_flat` (a flat dict).  _ga4_utils.get_session_id() and
    get_traffic_source() expect the original array format, so we reconstruct it.
    Non-serialisable types (datetime, ObjectId) are also stripped.
    """
    doc = dict(doc)
    doc.pop("_id", None)
    doc.pop("event_datetime", None)   # datetime object — not needed by pipeline
    doc.pop("user_properties_flat", None)

    flat: dict = doc.pop("event_params_flat", {}) or {}
    doc["event_params"] = [
        {"key": k, "value": _make_param_value(v)}
        for k, v in flat.items()
        if v is not None
    ]
    return doc


# ──────────────────────────────────────────────────────────────────────────────
# Background pipeline task
# ──────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, request: AnalysisRequest) -> None:
    settings = get_settings()
    job_col = get_collection("job_status")

    try:
        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"status": "running", "progress": 10}},
        )

        # ── 1. Load raw events from MongoDB ───────────────────────────────────
        events_col = get_collection(settings.MONGO_COLLECTION)

        query: dict = {}
        if request.week_start and request.week_end:
            query["event_date"] = {"$gte": request.week_start, "$lte": request.week_end}
        elif request.log_ids:
            query["_id"] = {"$in": request.log_ids}
        # If neither is provided, load the full collection (useful for testing)

        raw_docs = await events_col.find(query).to_list(length=100_000)
        raw_logs = [_prepare_doc(doc) for doc in raw_docs]

        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"progress": 20, "log_count": len(raw_logs)}},
        )

        # ── 2. Run LangGraph pipeline ──────────────────────────────────────────
        initial_state: dict = {
            "job_id": job_id,
            "period": request.period,
            "domain_description": request.domain_description,
            "raw_logs": raw_logs,
            "log_ids": request.log_ids,
            "week_start": request.week_start,
            "week_end": request.week_end,
        }

        result_state: dict = await analysis_graph.ainvoke(initial_state)

        # ── 3. Persist result ──────────────────────────────────────────────────
        insight_report = result_state.get("insight_report", {})
        result_col = get_collection("analysis_results")
        await result_col.replace_one(
            {"job_id": job_id},
            {
                "job_id": job_id,
                "insight_report": insight_report,
                "created_at": datetime.now(tz=timezone.utc),
            },
            upsert=True,
        )

        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"status": "done", "progress": 100}},
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
