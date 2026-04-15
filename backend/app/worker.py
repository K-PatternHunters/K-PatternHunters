"""Celery application and pipeline task.

파이프라인 실행 로직을 FastAPI BackgroundTasks에서 Celery Worker로 이전.
Worker는 FastAPI 서버와 별도 프로세스로 실행된다:

    celery -A app.worker.celery_app worker --loglevel=info
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone

from celery import Celery

from app.core.config import get_settings
from app.db import mongo
from app.db.mongo import get_collection
from app.graph.pipeline import analysis_graph

# ──────────────────────────────────────────────────────────────────────────────
# Celery app
# ──────────────────────────────────────────────────────────────────────────────

celery_app = Celery("kph")
celery_app.conf.update(
    broker_url=get_settings().REDIS_URL,
    result_backend=get_settings().REDIS_URL,
    task_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline logic (async)
# ──────────────────────────────────────────────────────────────────────────────

async def _run_pipeline(job_id: str, request_dict: dict) -> None:
    """LangGraph 파이프라인 실행 및 진행률/결과 MongoDB 기록."""
    job_col = get_collection("job_status")

    try:
        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"status": "running", "progress": 10}},
        )

        initial_state: dict = {
            "job_id": job_id,
            "period": request_dict["period"],
            "domain_description": request_dict["domain_description"],
            "week_start": request_dict["week_start"],
            "week_end": request_dict["week_end"],
        }

        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {"progress": 20}},
        )

        _NODE_PROGRESS = {
            "context_agent":       30,
            "analysis_dispatcher": 70,
            "insight_agent":       85,
            "ppt_agent":           95,
        }
        result_state: dict = dict(initial_state)
        async for chunk in analysis_graph.astream(initial_state):
            for node_name, node_output in chunk.items():
                result_state.update(node_output)
                if node_name in _NODE_PROGRESS:
                    await job_col.update_one(
                        {"job_id": job_id},
                        {"$set": {"progress": _NODE_PROGRESS[node_name]}},
                    )

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
            {"$set": {
                "status": "done",
                "progress": 100,
                "ppt_url": ppt_url,
                "result_url": f"/analysis/download/{job_id}",
            }},
        )

    except Exception as exc:
        await job_col.update_one(
            {"job_id": job_id},
            {"$set": {
                "status": "failed",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }},
        )
        raise


# ──────────────────────────────────────────────────────────────────────────────
# Celery task
# ──────────────────────────────────────────────────────────────────────────────

@celery_app.task(bind=True, name="app.worker.run_pipeline_task")
def run_pipeline_task(self, job_id: str, request_dict: dict) -> None:
    """Celery task: MongoDB 연결 후 파이프라인 실행, 완료 후 연결 해제."""
    async def _run() -> None:
        await mongo.connect()
        try:
            await _run_pipeline(job_id, request_dict)
        finally:
            await mongo.disconnect()

    asyncio.run(_run())
