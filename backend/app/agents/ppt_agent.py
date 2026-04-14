"""Generates a PowerPoint report from the insight_report using python-pptx, with RAG comparison against last week's report."""

# TODO: retrieve last week's PPT/report vectors from Qdrant via rag_tool for WoW comparison
# TODO: create Presentation() with python-pptx
# TODO: add slides for: title, executive summary, funnel, cohort, journey, performance, anomaly, prediction, recommendations
# TODO: embed charts/tables from agent metrics
# TODO: save .pptx to disk/object storage and store download URL in analysis_results MongoDB collection
# TODO: return ppt_url to pipeline state

import logging

from pptx import Presentation  # python-pptx

logger = logging.getLogger(__name__)


async def ppt_agent(state: dict) -> dict:
    """Temporary no-op PPT node.

    Keep the pipeline successful until actual PPT rendering/storage is implemented.
    insight_report is already persisted by the router, so returning a placeholder
    ppt_url lets downstream status/result APIs work without failing the job.
    """
    _ = Presentation  # keep import intentional until real PPT generation lands
    job_id = state.get("job_id", "<unknown>")
    logger.info("ppt_agent: placeholder mode for job_id=%s; skipping PPT generation", job_id)
    return {"ppt_url": ""}
