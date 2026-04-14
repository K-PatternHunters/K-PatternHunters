"""Extracts domain context for the given e-commerce domain using RAG (Qdrant) and web search."""

# TODO: accept domain_description from pipeline state
# TODO: call rag_tool to retrieve relevant past reports/knowledge
# TODO: call web_search_tool for live domain context
# TODO: return enriched domain_context dict to be passed downstream via LangGraph state

from langchain_core.messages import HumanMessage  # langchain v1.0+ import path


async def context_agent(state: dict) -> dict:
    # Placeholder — implementation pending
    raise NotImplementedError
