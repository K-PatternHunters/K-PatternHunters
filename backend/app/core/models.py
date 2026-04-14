"""Shared Pydantic v2 models for API request/response schemas and MongoDB document shapes."""

# TODO: AnalysisRequest  — POST /analysis/run body
# TODO: JobStatus        — mirrors job_status MongoDB document
# TODO: AnalysisResult   — mirrors analysis_results MongoDB document
# TODO: RawLog           — mirrors raw_logs MongoDB document shape

from pydantic import BaseModel
from typing import Literal


class AnalysisRequest(BaseModel):
    # Placeholder fields — expand during implementation
    period: Literal["daily", "weekly", "monthly"] = "weekly"
    domain_description: str
    log_ids: list[str] = []


class JobStatus(BaseModel):
    job_id: str
    status: Literal["pending", "running", "done", "failed"] = "pending"
    progress: int = 0          # 0-100
    result_url: str | None = None
    error: str | None = None


class AnalysisResult(BaseModel):
    job_id: str
    ppt_url: str | None = None
    summary: str | None = None


class RawLog(BaseModel):
    # Placeholder — map to actual GA4 event fields during schema_mapping_agent implementation
    event_date: str | None = None
    event_name: str | None = None
    user_pseudo_id: str | None = None
