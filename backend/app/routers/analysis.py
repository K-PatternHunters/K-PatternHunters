"""POST /analysis/run — accepts analysis request, enqueues Celery task, returns job_id.

파이프라인은 Celery Worker 프로세스에서 실행된다. Worker 기동:
    celery -A app.worker.celery_app worker --loglevel=info
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.core.models import AnalysisRequest
from app.db.mongo import get_collection
from app.worker import run_pipeline_task

router = APIRouter()


@router.post("/run", status_code=202)
async def run_analysis(request: AnalysisRequest):
    """Celery 큐에 파이프라인 작업을 등록하고 job_id를 반환한다.

    파이프라인은 비동기 실행 — GET /analysis/status/{job_id} 로 폴링하여
    status == "done" 확인 후 GET /analysis/result/{job_id} 로 결과를 조회한다.
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

    run_pipeline_task.delay(job_id, request.model_dump())
    return {"job_id": job_id}
