"""Generates a PowerPoint report from the insight_report using python-pptx, with RAG comparison against last week's report."""

# TODO: retrieve last week's PPT/report vectors from Qdrant via rag_tool for WoW comparison
# TODO: create Presentation() with python-pptx
# TODO: add slides for: title, executive summary, funnel, cohort, journey, performance, anomaly, prediction, recommendations
# TODO: embed charts/tables from agent metrics
# TODO: save .pptx to disk/object storage and store download URL in analysis_results MongoDB collection
# TODO: return ppt_url to pipeline state

from pptx import Presentation  # python-pptx


async def ppt_agent(state: dict) -> dict:
    # Placeholder — implementation pending
    raise NotImplementedError
